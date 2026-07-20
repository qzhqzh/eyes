import os
import subprocess
import sys
import tempfile
import unittest


class WebAppSmokeTest(unittest.TestCase):
    def test_logged_in_fleet_view_and_summary_render(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env.update(
                {
                    "EYES_DB_PATH": os.path.join(temp_dir, "eyes-web-test.db"),
                    "EYES_SECRET_KEY": "web-smoke-secret-key",
                    "EYES_WEB_PASSWORD": "web-smoke-password",
                    "EYES_ENABLE_SCHEDULED_CHECKS": "0",
                }
            )
            script = """
from app import app
client = app.test_client()
assert client.get('/fleet').status_code == 302
assert client.get('/api/v1/fleet/summary').status_code == 401
with client.session_transaction() as session:
    session['logged_in'] = True
page = client.get('/fleet')
assert page.status_code == 200
assert b'eyes-sidebar' in page.data
assert b'fleet-summary' in page.data
assert b'href="/fleet"' in page.data
assert 'Fleet 节点'.encode() in page.data
assert client.get('/api/v1/fleet/summary').status_code == 200
"""
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=os.path.dirname(os.path.dirname(__file__)),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
