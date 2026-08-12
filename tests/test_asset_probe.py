import io
import unittest
from unittest import mock

from asset_probe import AssetProbeHandler


def _handler(body):
    handler = object.__new__(AssetProbeHandler)
    handler.path = "/api/context7/request"
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = io.BytesIO(body)
    handler.send_json = mock.Mock()
    return handler


class AssetProbeTest(unittest.TestCase):
    def test_non_object_request_returns_400(self):
        handler = _handler(b"[]")
        handler.do_POST()
        payload = handler.send_json.call_args.args[0]
        self.assertEqual(handler.send_json.call_args.kwargs["status"], 400)
        self.assertIn("JSON object", payload["error"])

    def test_params_must_be_an_object(self):
        handler = _handler(b'{"path":"/api/v2/context","params":[]}')
        handler.do_POST()
        payload = handler.send_json.call_args.args[0]
        self.assertEqual(handler.send_json.call_args.kwargs["status"], 400)
        self.assertIn("params", payload["error"])

    def test_deeply_nested_json_returns_400(self):
        body = ("[" * 1100 + "0" + "]" * 1100).encode()
        handler = _handler(body)
        handler.do_POST()
        self.assertEqual(handler.send_json.call_args.kwargs["status"], 400)


if __name__ == "__main__":
    unittest.main()
