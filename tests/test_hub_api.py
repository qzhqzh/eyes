import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

from flask import Flask
from werkzeug.serving import make_server

import models
from fleet import init_fleet_db
from hub_api import hub_api


class HubApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "eyes-api-test.db")
        self.db_patch = mock.patch.object(models, "DB_PATH", self.db_path)
        self.db_patch.start()
        self.env_patch = mock.patch.dict(os.environ, {"EYES_HUB_ENROLL_TOKEN": "join-once"})
        self.env_patch.start()

        models.init_db()
        init_fleet_db()
        app = Flask(__name__)
        app.secret_key = "test-secret"
        app.register_blueprint(hub_api)
        app.testing = True
        self.client = app.test_client()

    def tearDown(self):
        self.env_patch.stop()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_node_enrollment_and_push_flow(self):
        denied = self.client.post(
            "/api/v1/enroll",
            headers={"X-Eyes-Enroll-Token": "wrong"},
            json={"node_id": "node-api", "hostname": "api-worker"},
        )
        self.assertEqual(denied.status_code, 403)

        response = self.client.post(
            "/api/v1/enroll",
            headers={"X-Eyes-Enroll-Token": "join-once"},
            json={
                "node_id": "node-api",
                "node_token": "node-api-credential-that-is-long-enough",
                "hostname": "api-worker",
                "agent_version": "0.2.0",
                "protocol_version": "eyes.node.v1",
            },
        )
        self.assertEqual(response.status_code, 201)
        token = response.get_json()["node_token"]
        replay = self.client.post(
            "/api/v1/enroll",
            headers={"X-Eyes-Enroll-Token": "join-once"},
            json={
                "node_id": "node-api",
                "node_token": token,
                "hostname": "api-worker",
            },
        )
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.get_json()["node_token"], token)
        node_headers = {
            "Authorization": f"Bearer {token}",
            "X-Eyes-Node-ID": "node-api",
        }

        heartbeat = self.client.post(
            "/api/v1/node/heartbeat",
            headers=node_headers,
            json={"boot_id": "boot-api", "sequence": 1},
        )
        self.assertEqual(heartbeat.status_code, 200)

        snapshot = self.client.put(
            "/api/v1/node/resources",
            headers=node_headers,
            json={"generation": 1, "payload": {"cpu": {"capacity": 4}}},
        )
        self.assertEqual(snapshot.status_code, 200)

        commands = self.client.get("/api/v1/node/commands", headers=node_headers)
        self.assertEqual(commands.status_code, 200)
        self.assertEqual(commands.get_json()["commands"], [])

    def test_admin_fleet_and_workload_api_require_login(self):
        self.assertEqual(self.client.get("/api/v1/nodes").status_code, 401)
        with self.client.session_transaction() as web_session:
            web_session["logged_in"] = True

        nodes = self.client.get("/api/v1/nodes")
        self.assertEqual(nodes.status_code, 200)

        workload = self.client.post(
            "/api/v1/workloads",
            json={"name": "test-job", "spec": {"type": "batch"}, "priority": 2},
        )
        self.assertEqual(workload.status_code, 202)
        self.assertEqual(workload.get_json()["status"], "pending")
        self.assertEqual(len(self.client.get("/api/v1/workloads").get_json()), 1)

    def test_node_agent_once_registers_and_pushes_snapshots(self):
        server = make_server("127.0.0.1", 0, self.client.application)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        state_dir = os.path.join(self.temp_dir.name, "agent-state")
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "agent/eyes-agent.py",
                    "--mode",
                    "node",
                    "--hub-url",
                    f"http://127.0.0.1:{server.server_port}",
                    "--enroll-token",
                    "join-once",
                    "--state-dir",
                    state_dir,
                    "--once",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        finally:
            server.shutdown()
            server_thread.join(timeout=2)

        self.assertEqual(result.returncode, 0, result.stderr)
        with self.client.session_transaction() as web_session:
            web_session["logged_in"] = True
        nodes = self.client.get("/api/v1/nodes").get_json()
        pushed = next(node for node in nodes if node["id"] != "hub-local")
        detail = self.client.get(f"/api/v1/nodes/{pushed['id']}").get_json()
        self.assertEqual(detail["status"], "ready")
        self.assertIn("inventory", detail["snapshots"])
        self.assertIn("resources", detail["snapshots"])


if __name__ == "__main__":
    unittest.main()
