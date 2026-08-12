import os
import tempfile
import unittest
from email.message import Message
from unittest import mock

import yaml

import asset_management


class _FakeResponse:
    def __init__(self, status=200, body=b"{}", headers=None):
        self.status = status
        self._body = body
        self.headers = headers or Message()
        self._sock = mock.Mock()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, size=-1):
        if not self._body:
            return b""
        if size is None or size < 0:
            size = len(self._body)
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk


class AssetManagementTest(unittest.TestCase):
    def setUp(self):
        asset_management._model_cache.update({"at": 0.0, "items": []})
        asset_management._context7_cache.update({"at": 0.0, "items": []})
        asset_management._context7_query_cache.clear()
        asset_management._context7_runtime.clear()
        asset_management._context7_cursor = 0
        asset_management._context7_account_generation = ()

    def test_totemora_settings_model_stays_separate_and_public_url_is_redacted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ai_key_dir = os.path.join(temp_dir, "ai-key")
            totemora_dir = os.path.join(temp_dir, "totemora")
            os.makedirs(ai_key_dir)
            os.makedirs(totemora_dir)
            with open(
                os.path.join(ai_key_dir, "providers.conf"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    "[deepseek]\n"
                    "name=DeepSeek\n"
                    "model=deepseek-v4-pro\n"
                    "api_mode=chat_completions\n"
                    "base_url=https://user:password@api.example.com/v1?token=sensitive#part\n"
                    "env_key=DEEPSEEK_KEY\n"
                )
            with open(
                os.path.join(ai_key_dir, ".env"), "w", encoding="utf-8"
            ) as handle:
                handle.write("DEEPSEEK_KEY=test-secret-key\n")
            with open(
                os.path.join(totemora_dir, "providers.yaml"),
                "w",
                encoding="utf-8",
            ) as handle:
                yaml.safe_dump(
                    {
                        "providers": {
                            "deepseek": {
                                "type": "anthropic_compatible",
                                "settings_file": "~/.claude/settings.ds.json",
                            },
                            "openai": {
                                "type": "openai_responses",
                                "base_url": "https://api.openai.example/v1",
                                "api_key_env": "OPENAI_TEST_KEY",
                            }
                        }
                    },
                    handle,
                )
            with open(
                os.path.join(totemora_dir, "agents.yaml"),
                "w",
                encoding="utf-8",
            ) as handle:
                yaml.safe_dump(
                    {
                        "agents": [
                            {
                                "id": "reasoner",
                                "provider": "deepseek",
                                "model": "deepseek-v4-pro[1m]",
                            },
                            {
                                "id": "chief",
                                "provider": "openai",
                                "model": "gpt-test",
                            }
                        ]
                    },
                    handle,
                )

            with mock.patch.dict(
                os.environ, {"OPENAI_TEST_KEY": "totemora-openai-secret"}
            ):
                assets = asset_management.discover_model_assets(
                    ai_key_dir, totemora_dir
                )
            inherited = next(
                item for item in assets if item["model"] == "deepseek-v4-pro[1m]"
            )
            self.assertEqual(inherited["base_url"], "")
            self.assertEqual(inherited["api_mode"], "anthropic_messages")
            self.assertFalse(inherited["configured"])
            self.assertEqual(inherited["sources"], ["totemora"])
            self.assertEqual(inherited["agents"], ["reasoner"])
            self.assertEqual(inherited["_api_key"], "")

            ai_key_model = next(
                item for item in assets if item["model"] == "deepseek-v4-pro"
            )
            self.assertIn("user:password", ai_key_model["base_url"])
            openai_model = next(
                item for item in assets if item["model"] == "gpt-test"
            )
            self.assertTrue(openai_model["configured"])
            self.assertEqual(openai_model["api_mode"], "openai_responses")
            opener = mock.Mock()
            opener.open.return_value = _FakeResponse()
            with mock.patch(
                "asset_management.urllib.request.build_opener",
                return_value=opener,
            ):
                public_result = asset_management.probe_model(ai_key_model)
            self.assertEqual(public_result["state"], "healthy")
            self.assertEqual(
                public_result["base_url"], "https://api.example.com/v1"
            )
            self.assertNotIn("_api_key", public_result)
            self.assertNotIn("test-secret-key", str(public_result))
            self.assertNotIn("password", str(public_result))
            self.assertNotIn("sensitive", str(public_result))

            unconfigured = asset_management.probe_model(inherited)
            self.assertEqual(unconfigured["state"], "unconfigured")
            with mock.patch(
                "asset_management.urllib.request.build_opener",
                return_value=opener,
            ):
                openai_result = asset_management.probe_model(openai_model)
            self.assertEqual(openai_result["state"], "healthy")
            self.assertNotIn("totemora-openai-secret", str(openai_result))

    def test_context7_accounts_deduplicate_keys_and_labels(self):
        accounts = asset_management.load_context7_accounts(
            "personal=ctx7sk-one,duplicate=ctx7sk-one,"
            "personal=ctx7sk-two,work=ctx7sk-three,invalid=not-a-key"
        )
        self.assertEqual(
            [(item["label"], item["_api_key"]) for item in accounts],
            [("personal", "ctx7sk-one"), ("work", "ctx7sk-three")],
        )

    def test_context7_accounts_load_from_secret_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            accounts_file = os.path.join(temp_dir, "context7-accounts")
            with open(accounts_file, "w", encoding="utf-8") as handle:
                handle.write(
                    "# Example: label=ctx7sk_placeholder\n"
                    "personal=ctx7sk-file-one\n"
                    "work=ctx7sk-file-two\n"
                )
            with mock.patch.dict(
                os.environ,
                {
                    "EYES_CONTEXT7_ACCOUNTS": "",
                    "EYES_CONTEXT7_ACCOUNTS_FILE": accounts_file,
                },
            ):
                accounts = asset_management.load_context7_accounts()
            self.assertEqual(
                [item["label"] for item in accounts], ["personal", "work"]
            )
            self.assertTrue(
                all(item["_api_key"].startswith("ctx7sk") for item in accounts)
            )

            with mock.patch.dict(
                os.environ,
                {
                    "EYES_CONTEXT7_ACCOUNTS": "direct=ctx7sk-direct-key",
                    "EYES_CONTEXT7_ACCOUNTS_FILE": accounts_file,
                },
            ):
                direct_accounts = asset_management.load_context7_accounts()
            self.assertEqual(
                [item["label"] for item in direct_accounts], ["direct"]
            )

            invalid_file = os.path.join(temp_dir, "invalid-context7-accounts")
            with open(invalid_file, "wb") as handle:
                handle.write(b"\xff\xfe")
            with mock.patch.dict(
                os.environ,
                {
                    "EYES_CONTEXT7_ACCOUNTS": "",
                    "EYES_CONTEXT7_ACCOUNTS_FILE": invalid_file,
                },
            ):
                self.assertEqual(asset_management.load_context7_accounts(), [])

    def test_context7_explicit_refresh_uses_server_side_cooldown(self):
        accounts = [{"label": "primary", "_api_key": "ctx7sk-primary"}]
        headers = Message()
        headers["RateLimit-Limit"] = "100"
        headers["RateLimit-Remaining"] = "99"

        with mock.patch(
            "asset_management.load_context7_accounts", return_value=accounts
        ), mock.patch(
            "asset_management._call_context7",
            return_value=(200, b"{}", headers, 1.0),
        ) as call:
            first = asset_management.get_context7_accounts(refresh=True)
            second = asset_management.get_context7_accounts(refresh=True)

        self.assertEqual(call.call_count, 1)
        self.assertIs(first, second)
        self.assertEqual(first[0]["label"], "primary")
        self.assertEqual(first[0]["state"], "healthy")

    def test_context7_pool_fails_over_and_caches_success(self):
        accounts = [
            {"label": "first", "_api_key": "ctx7sk-first"},
            {"label": "second", "_api_key": "ctx7sk-second"},
        ]
        limited_headers = Message()
        limited_headers["RateLimit-Limit"] = "100"
        limited_headers["RateLimit-Remaining"] = "0"
        limited_headers["RateLimit-Reset"] = "4102444800"
        healthy_headers = Message()
        healthy_headers["Content-Type"] = "application/json"
        healthy_headers["RateLimit-Limit"] = "100"
        healthy_headers["RateLimit-Remaining"] = "82"
        healthy_headers["RateLimit-Reset"] = "4102444800"

        with mock.patch(
            "asset_management.load_context7_accounts", return_value=accounts
        ), mock.patch(
            "asset_management._call_context7",
            side_effect=[
                (429, b'{"error":"limited"}', limited_headers, 10.0),
                (200, b'{"results":[]}', healthy_headers, 12.0),
            ],
        ) as call:
            result = asset_management.pooled_context7_request(
                "/api/v2/libs/search",
                {"libraryName": "flask", "query": "routing"},
            )
            cached = asset_management.pooled_context7_request(
                "/api/v2/libs/search",
                {"libraryName": "flask", "query": "routing"},
            )

        self.assertEqual(call.call_count, 2)
        self.assertEqual(result["account_label"], "second")
        self.assertFalse(result["cache_hit"])
        self.assertTrue(cached["cache_hit"])
        self.assertNotIn("ctx7sk", str(result))
        self.assertEqual(
            asset_management._context7_runtime["first"]["state"],
            "quota_exhausted",
        )
        self.assertEqual(
            asset_management._context7_runtime["second"]["remaining"], 82
        )

    def test_context7_retry_after_recovers_without_reset_header(self):
        accounts = [{"label": "primary", "_api_key": "ctx7sk-primary"}]
        asset_management._sync_context7_accounts(accounts)
        asset_management._context7_runtime["primary"] = {
            "state": "quota_exhausted",
            "reset_at": None,
            "retry_at": 1030,
        }
        headers = Message()
        headers["Content-Type"] = "application/json"
        with mock.patch(
            "asset_management.load_context7_accounts", return_value=accounts
        ), mock.patch(
            "asset_management._call_context7",
            return_value=(200, b'{"results":[]}', headers, 1.0),
        ) as call, mock.patch("asset_management.time.time", return_value=1010):
            with self.assertRaises(asset_management.Context7PoolError):
                asset_management.pooled_context7_request(
                    "/api/v2/libs/search", {"libraryName": "flask", "query": "routing"}
                )
            call.assert_not_called()

        with mock.patch(
            "asset_management.load_context7_accounts", return_value=accounts
        ), mock.patch(
            "asset_management._call_context7",
            return_value=(200, b'{"results":[]}', headers, 1.0),
        ) as call, mock.patch("asset_management.time.time", return_value=1031):
            result = asset_management.pooled_context7_request(
                "/api/v2/libs/search", {"libraryName": "flask", "query": "routing"}
            )
            self.assertEqual(result["account_label"], "primary")
            call.assert_called_once()

    def test_context7_key_rotation_invalidates_runtime_and_query_cache(self):
        old_accounts = [{"label": "primary", "_api_key": "ctx7sk-old"}]
        new_accounts = [{"label": "primary", "_api_key": "ctx7sk-new"}]
        asset_management._sync_context7_accounts(old_accounts)
        asset_management._context7_runtime["primary"] = {"state": "auth_error"}
        asset_management._context7_query_cache[("old", ())] = {
            "at": 1.0,
            "result": {"body": b"private"},
        }
        headers = Message()
        headers["Content-Type"] = "application/json"
        with mock.patch(
            "asset_management.load_context7_accounts", return_value=new_accounts
        ), mock.patch(
            "asset_management._call_context7",
            return_value=(200, b'{"results":[]}', headers, 1.0),
        ) as call:
            result = asset_management.pooled_context7_request(
                "/api/v2/libs/search", {"libraryName": "flask", "query": "routing"}
            )
        self.assertEqual(result["account_label"], "primary")
        self.assertNotIn(("old", ()), asset_management._context7_query_cache)
        self.assertEqual(call.call_args.args[0], "ctx7sk-new")

    def test_context7_inflight_old_generation_cannot_write_back(self):
        old_accounts = [{"label": "primary", "_api_key": "ctx7sk-old"}]
        new_accounts = [{"label": "primary", "_api_key": "ctx7sk-new"}]
        headers = Message()
        headers["Content-Type"] = "application/json"

        def rotate_during_request(*_args, **_kwargs):
            asset_management._sync_context7_accounts(new_accounts)
            return 200, b'{"private":"old"}', headers, 1.0

        with mock.patch(
            "asset_management.load_context7_accounts", return_value=old_accounts
        ), mock.patch(
            "asset_management._call_context7", side_effect=rotate_during_request
        ):
            with self.assertRaisesRegex(
                asset_management.Context7PoolError, "configuration changed"
            ):
                asset_management.pooled_context7_request(
                    "/api/v2/libs/search",
                    {"libraryName": "private", "query": "docs"},
                )

        self.assertEqual(asset_management._context7_query_cache, {})
        self.assertEqual(asset_management._context7_runtime, {})
        self.assertEqual(
            asset_management._context7_account_generation,
            asset_management._context7_generation(new_accounts),
        )

    def test_context7_zero_remaining_is_temporarily_exhausted(self):
        headers = Message()
        headers["RateLimit-Limit"] = "100"
        headers["RateLimit-Remaining"] = "0"
        headers["Retry-After"] = "20"
        with mock.patch("asset_management.time.time", return_value=1000):
            state = asset_management._context7_state("primary", 200, headers, 1.0)
        self.assertEqual(state["state"], "quota_exhausted")
        self.assertEqual(state["retry_at"], 1020)

    def test_context7_auth_error_wins_over_zero_remaining(self):
        headers = Message()
        headers["RateLimit-Remaining"] = "0"
        state = asset_management._context7_state("primary", 401, headers, 1.0)
        self.assertEqual(state["state"], "auth_error")
        self.assertIsNone(state["retry_at"])

    def test_context7_query_cache_enforces_byte_budget(self):
        first = {
            "status_code": 200,
            "body": b"a" * 6,
            "content_type": "application/json",
        }
        second = first | {"body": b"b" * 6}
        with mock.patch.object(
            asset_management, "CONTEXT7_QUERY_CACHE_MAX_BYTES", 10
        ):
            asset_management._cache_context7_result(("first", ()), first)
            asset_management._cache_context7_result(("second", ()), second)
        self.assertNotIn(("first", ()), asset_management._context7_query_cache)
        self.assertIn(("second", ()), asset_management._context7_query_cache)

    def test_context7_response_read_enforces_absolute_deadline(self):
        response = _FakeResponse(body=b"response")
        with mock.patch(
            "asset_management.time.monotonic", side_effect=[0.0, 2.0]
        ):
            with self.assertRaisesRegex(TimeoutError, "deadline exceeded"):
                asset_management._read_context7_body(response, deadline=1.0)

    def test_context7_response_without_socket_is_rejected(self):
        response = _FakeResponse()
        del response._sock
        with self.assertRaisesRegex(OSError, "does not support deadlines"):
            asset_management._read_context7_body(response, deadline=1.0)


if __name__ == "__main__":
    unittest.main()
