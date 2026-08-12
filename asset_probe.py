#!/usr/bin/env python3
"""Loopback-only secret-bearing probe for model and Context7 assets."""

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from asset_management import (
    Context7PoolError,
    get_context7_accounts,
    get_model_assets,
    pooled_context7_request,
)


AI_KEY_DIR = os.environ.get("EYES_AI_KEY_DIR", "/assets/ai-key")
TOTEMORA_CONFIG_DIR = os.environ.get(
    "EYES_TOTEMORA_CONFIG_DIR", "/assets/totemora"
)
MAX_REQUEST_BYTES = 32 * 1024


class AssetProbeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        refresh = parse_qs(parsed.query).get("refresh") == ["1"]
        if parsed.path == "/api/health":
            self.send_json({"ok": True})
            return
        if parsed.path == "/api/models":
            self.send_json({
                "models": get_model_assets(
                    AI_KEY_DIR, TOTEMORA_CONFIG_DIR, refresh=refresh
                )
            })
            return
        if parsed.path == "/api/context7/accounts":
            self.send_json({"accounts": get_context7_accounts(refresh=refresh)})
            return
        self.send_error(404)

    def do_POST(self):
        if self.path != "/api/context7/request":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                self.send_json({"error": "invalid request size"}, status=413)
                return
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            path = payload.get("path")
            params = payload.get("params", {})
            if not isinstance(path, str) or not isinstance(params, dict):
                raise ValueError("path must be a string and params must be an object")
            result = pooled_context7_request(
                path, params
            )
            try:
                body = json.loads(result["body"].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                body = result["body"].decode("utf-8", errors="replace")
            self.send_json({
                "status_code": result["status_code"],
                "content_type": result["content_type"],
                "account_label": result["account_label"],
                "body": body,
            })
        except Context7PoolError as exc:
            self.send_json(
                {"error": str(exc), "status_code": exc.status_code}, status=503
            )
        except (ValueError, TypeError, json.JSONDecodeError, RecursionError) as exc:
            self.send_json({"error": str(exc)}, status=400)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


def main():
    parser = argparse.ArgumentParser(description="eyes local asset probe")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9092)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), AssetProbeHandler)
    print(f"eyes asset probe listening on {args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
