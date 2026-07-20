import json
import stat
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agent.node_client import (
    ExponentialBackoff,
    HubClient,
    HubClientError,
    HubHTTPError,
    HubProtocolError,
    NodeStateError,
    NodeStateStore,
)


class RecordingHandler(BaseHTTPRequestHandler):
    requests = []

    def do_GET(self):
        self._record_and_reply()

    def do_POST(self):
        self._record_and_reply()

    def do_PUT(self):
        self._record_and_reply()

    def _record_and_reply(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        parsed = urlparse(self.path)
        type(self).requests.append(
            {
                "method": self.command,
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "headers": dict(self.headers),
                "body": json.loads(body) if body else None,
            }
        )
        if parsed.path == "/failure":
            self.send_response(403)
            response = b'{"error":"denied"}'
        elif parsed.path == "/invalid-json":
            self.send_response(200)
            response = b"not json"
        else:
            self.send_response(200)
            response = b'{"ok":true}'
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        pass


class NodeStateStoreTests(unittest.TestCase):
    def test_creates_stable_private_identity_and_persists_credential(self):
        with tempfile.TemporaryDirectory() as state_dir:
            store = NodeStateStore(state_dir)

            created = store.load_or_create()
            loaded = store.load_or_create()

            self.assertEqual(created.node_id, loaded.node_id)
            self.assertIsNone(created.credential)
            self.assertEqual(
                stat.S_IMODE(Path(store.path).stat().st_mode),
                0o600,
            )

            enrolled = store.set_credential("hub-secret")
            persisted = json.loads(Path(store.path).read_text(encoding="utf-8"))
            self.assertEqual(enrolled.node_id, created.node_id)
            self.assertEqual(store.load().credential, "hub-secret")
            self.assertEqual(
                persisted,
                {
                    "credential": "hub-secret",
                    "enrolled": True,
                    "node_id": created.node_id,
                },
            )
            self.assertEqual(list(Path(state_dir).glob("*.tmp")), [])

    def test_pending_enrollment_credential_survives_response_loss(self):
        with tempfile.TemporaryDirectory() as state_dir:
            store = NodeStateStore(state_dir)
            first = store.prepare_enrollment()
            retry = store.prepare_enrollment()

            self.assertFalse(first.enrolled)
            self.assertEqual(retry.credential, first.credential)
            enrolled = store.mark_enrolled()
            self.assertTrue(enrolled.enrolled)
            self.assertEqual(enrolled.credential, first.credential)

    def test_rejects_invalid_state(self):
        with tempfile.TemporaryDirectory() as state_dir:
            path = Path(state_dir) / "node.json"
            path.write_text('{"credential":"secret"}', encoding="utf-8")

            with self.assertRaises(NodeStateError):
                NodeStateStore(state_dir).load()


class HubClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
        cls.server_thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.server_thread.start()
        host, port = cls.server.server_address
        cls.base_url = f"http://{host}:{port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2)

    def setUp(self):
        RecordingHandler.requests = []

    def test_protocol_methods_use_expected_paths_payloads_and_auth(self):
        client = HubClient(self.base_url, credential="node-secret", node_id="node-1")

        self.assertTrue(
            client.enroll(
                "once",
                "node-1",
                node_token="n" * 32,
                metadata={"hostname": "host-a"},
            )["ok"]
        )
        self.assertTrue(client.heartbeat({"sequence": 1})["ok"])
        self.assertTrue(client.put_inventory({"generation": 2})["ok"])
        self.assertTrue(client.put_resources({"generation": 3})["ok"])
        self.assertTrue(client.get_commands(cursor=17, wait=12)["ok"])
        self.assertTrue(
            client.acknowledge_command("cmd-1", "succeeded", {"exit_code": 0})["ok"]
        )

        enroll, heartbeat, inventory, resources, commands, ack = RecordingHandler.requests
        self.assertEqual((enroll["method"], enroll["path"]), ("POST", "/api/v1/enroll"))
        self.assertEqual(enroll["body"]["protocol_version"], "eyes.node.v1")
        self.assertEqual(enroll["headers"]["X-Eyes-Enroll-Token"], "once")
        self.assertEqual(enroll["body"]["node_token"], "n" * 32)
        self.assertEqual(enroll["body"]["hostname"], "host-a")
        self.assertNotIn("Authorization", enroll["headers"])
        self.assertEqual(
            (heartbeat["method"], heartbeat["path"]),
            ("POST", "/api/v1/node/heartbeat"),
        )
        self.assertEqual(
            (inventory["method"], inventory["path"]),
            ("PUT", "/api/v1/node/inventory"),
        )
        self.assertEqual(
            (resources["method"], resources["path"]),
            ("PUT", "/api/v1/node/resources"),
        )
        self.assertEqual(commands["method"], "GET")
        self.assertEqual(commands["query"], {"cursor": ["17"], "wait": ["12"]})
        self.assertEqual(
            (ack["method"], ack["path"]),
            ("POST", "/api/v1/node/commands/cmd-1/ack"),
        )
        self.assertEqual(ack["body"], {"status": "succeeded", "result": {"exit_code": 0}})
        for request in (heartbeat, inventory, resources, commands, ack):
            self.assertEqual(request["headers"]["Authorization"], "Bearer node-secret")
            headers = {key.lower(): value for key, value in request["headers"].items()}
            self.assertEqual(headers["x-eyes-node-id"], "node-1")

    def test_authenticated_method_requires_credential(self):
        with self.assertRaises(HubClientError):
            HubClient(self.base_url, node_id="node-1").heartbeat({})

    def test_remote_cleartext_hub_requires_explicit_opt_in(self):
        with self.assertRaises(ValueError):
            HubClient("http://hub.example.test:8090")
        client = HubClient(
            "http://hub.example.test:8090",
            allow_insecure_http=True,
        )
        self.assertEqual(client.base_url, "http://hub.example.test:8090")
        self.assertEqual(HubClient("https://hub.example.test").base_url, "https://hub.example.test")

    def test_maps_http_and_invalid_json_errors(self):
        client = HubClient(self.base_url, credential="node-secret", node_id="node-1")
        with self.assertRaises(HubHTTPError) as failure:
            client._request_json("GET", "/failure")
        self.assertEqual(failure.exception.status_code, 403)
        self.assertIn("denied", failure.exception.body)

        with self.assertRaises(HubProtocolError):
            client._request_json("GET", "/invalid-json")


class ExponentialBackoffTests(unittest.TestCase):
    def test_bounded_growth_and_reset(self):
        backoff = ExponentialBackoff(
            initial=1,
            maximum=5,
            multiplier=2,
            jitter=0,
        )

        self.assertEqual(
            [backoff.next_delay() for _ in range(5)],
            [1, 2, 4, 5, 5],
        )
        backoff.reset()
        self.assertEqual(backoff.next_delay(), 1)

    def test_deterministic_jitter(self):
        low = ExponentialBackoff(jitter=0.2, random_source=lambda: 0).delay(1)
        high = ExponentialBackoff(jitter=0.2, random_source=lambda: 1).delay(1)
        self.assertAlmostEqual(low, 1.6)
        self.assertAlmostEqual(high, 2.4)


if __name__ == "__main__":
    unittest.main()
