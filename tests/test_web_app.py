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
import os
from unittest import mock
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
intervals = client.get('/api/check-intervals').get_json()
assert intervals['resources'] == 300
assert intervals['docker'] == 600
assert intervals['systemd'] == 1800
assert intervals['wireguard'] == 60
assert intervals['network_speed'] == 600
assert intervals['scheduled_checks_enabled'] is False
assert client.post('/api/check-intervals', json={'group': 'docker', 'minutes': 30}).status_code == 409
response = client.post('/api/check-intervals', json={'group': 'wireguard', 'minutes': 5})
assert response.status_code == 200
assert response.get_json()['seconds'] == 300
assert client.get('/api/check-intervals').get_json()['wireguard'] == 300
os.environ['EYES_ENABLE_SCHEDULED_CHECKS'] = '1'
response = client.post('/api/check-intervals', json={'group': 'docker', 'minutes': 30})
assert response.status_code == 200
assert response.get_json()['seconds'] == 1800
assert client.post('/api/check-intervals', json={'group': 'invalid', 'minutes': 5}).status_code == 400
os.environ['EYES_AGENT_URL'] = 'http://127.0.0.1:9091'
with mock.patch('app.scan_all', return_value={'docker': [], 'systemd': [], 'crond': []}) as scan:
    assert client.post('/api/scan').status_code == 200
    scan.assert_called_once_with('http://127.0.0.1:9091')
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
