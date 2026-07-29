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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._body


class AssetManagementTest(unittest.TestCase):
    def setUp(self):
        asset_management._model_cache.update({"at": 0.0, "items": []})
        asset_management._context7_cache.update({"at": 0.0, "items": []})
        asset_management._context7_query_cache.clear()
        asset_management._context7_runtime.clear()
        asset_management._context7_cursor = 0

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


if __name__ == "__main__":
    unittest.main()
