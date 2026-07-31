import os
import subprocess
import sys
import tempfile
import unittest


class McpRateLimiterTest(unittest.TestCase):
    def test_inactive_client_keys_are_pruned(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env.update(
                {
                    "EYES_DB_PATH": os.path.join(temp_dir, "eyes-rate-limit-test.db"),
                    "EYES_SECRET_KEY": "rate-limit-test-secret-key",
                    "EYES_WEB_PASSWORD": "rate-limit-test-password",
                    "EYES_ENABLE_SCHEDULED_CHECKS": "0",
                }
            )
            script = """
from unittest import mock
import app as app_module

app_module._asset_mcp_request_times.clear()
app_module._asset_mcp_request_times.update({
    'stale-client': [10.0],
    'active-client': [70.0],
})
app_module._asset_mcp_last_cleanup = 0.0

with mock.patch('app.time.monotonic', return_value=100.0):
    assert app_module._asset_mcp_rate_allowed('new-client') is True

assert 'stale-client' not in app_module._asset_mcp_request_times
assert app_module._asset_mcp_request_times['active-client'] == [70.0]
assert app_module._asset_mcp_request_times['new-client'] == [100.0]
"""
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=os.path.dirname(os.path.dirname(__file__)),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
