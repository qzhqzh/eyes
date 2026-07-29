import os
import subprocess
import sys
import tempfile
import unittest


class WebAppSmokeTest(unittest.TestCase):
    def test_logged_in_fleet_view_and_summary_render(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            asset_token_file = os.path.join(temp_dir, "asset-api-token")
            with open(asset_token_file, "w", encoding="utf-8") as handle:
                handle.write("asset-smoke-token-123456789")
            invalid_secret_file = os.path.join(temp_dir, "invalid-secret")
            with open(invalid_secret_file, "wb") as handle:
                handle.write(b"\xff\xfe")
            env.pop("EYES_ASSET_API_TOKEN", None)
            env.update(
                {
                    "EYES_DB_PATH": os.path.join(temp_dir, "eyes-web-test.db"),
                    "EYES_SECRET_KEY": "web-smoke-secret-key",
                    "EYES_WEB_PASSWORD": "web-smoke-password",
                    "EYES_ASSET_API_TOKEN_FILE": asset_token_file,
                    "EYES_INVALID_SECRET_FILE": invalid_secret_file,
                    "EYES_ENABLE_SCHEDULED_CHECKS": "0",
                }
            )
            script = """
import os
from unittest import mock
from app import app, _secret_value
client = app.test_client()
assert _secret_value('EYES_MISSING_SECRET', 'EYES_INVALID_SECRET_FILE') == ''
os.environ['EYES_DIRECT_TEST_SECRET'] = 'direct-secret-value'
os.environ['EYES_DIRECT_TEST_SECRET_FILE'] = os.environ['EYES_ASSET_API_TOKEN_FILE']
assert _secret_value('EYES_DIRECT_TEST_SECRET', 'EYES_DIRECT_TEST_SECRET_FILE') == 'direct-secret-value'
assert client.get('/fleet').status_code == 302
assert client.get('/api/v1/fleet/summary').status_code == 401
with client.session_transaction() as session:
    session['logged_in'] = True
page = client.get('/fleet')
assert page.status_code == 200
assert b'eyes-sidebar' in page.data
assert b'fleet-summary' in page.data
assert b'href="/fleet"' in page.data
assert b'href="/domains"' in page.data
assert b'href="/assets"' in page.data
assert 'Fleet 节点'.encode() in page.data
assert client.get('/domains').status_code == 200
assert client.get('/api/domains').status_code == 200
assert client.get('/api/domains/outside.example.com/status').status_code == 404
assert client.get('/assets').status_code == 200
with mock.patch('app.fetch_model_assets', return_value=[{'id': 'test:model'}]) as models:
    response = client.get('/api/assets/models?refresh=1')
    assert response.status_code == 200
    assert response.get_json()['models'][0]['id'] == 'test:model'
    models.assert_called_once_with('http://127.0.0.1:9092', refresh=True)
with mock.patch('app.fetch_context7_accounts', return_value=[{'label': 'primary'}]):
    response = client.get('/api/assets/context7')
    assert response.status_code == 200
    assert response.get_json()['accounts'][0]['label'] == 'primary'
    assert response.get_json()['mcp_enabled'] is True
assert client.post('/mcp/context7', json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'}).status_code == 401
mcp_headers = {'Authorization': 'Bearer asset-smoke-token-123456789'}
response = client.post(
    '/mcp/context7',
    headers=mcp_headers,
    json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-11-25'}},
)
assert response.status_code == 200
assert response.get_json()['result']['serverInfo']['name'] == 'eyes-context7-pool'
assert response.get_json()['result']['protocolVersion'] == '2025-03-26'
response = client.post(
    '/mcp/context7',
    headers=mcp_headers | {'MCP-Protocol-Version': '2099-01-01'},
    json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
)
assert response.status_code == 400
response = client.post(
    '/mcp/context7',
    headers=mcp_headers,
    json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
)
assert [item['name'] for item in response.get_json()['result']['tools']] == ['resolve-library-id', 'query-docs']
response = client.post(
    '/mcp/context7',
    headers=mcp_headers | {'Origin': 'https://untrusted.example'},
    json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
)
assert response.status_code == 403
response = client.post(
    '/mcp/context7',
    headers=mcp_headers,
    json={'jsonrpc': '2.0', 'method': 'notifications/initialized'},
)
assert response.status_code == 202
with mock.patch(
    'app.call_context7_pool',
    return_value={'status_code': 200, 'body': {'results': []}, 'content_type': 'application/json'},
):
    response = client.post(
        '/mcp/context7',
        headers=mcp_headers,
        json={
            'jsonrpc': '2.0',
            'id': 3,
            'method': 'tools/call',
            'params': {
                'name': 'resolve-library-id',
                'arguments': {'libraryName': 'flask', 'query': 'routing'},
            },
        },
    )
assert response.status_code == 200
assert response.get_json()['result']['structuredContent'] == {'results': []}
with mock.patch('app._asset_mcp_rate_allowed', return_value=False):
    response = client.post(
        '/mcp/context7',
        headers=mcp_headers,
        json={'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list'},
    )
assert response.status_code == 429
assert response.headers['Retry-After'] == '60'
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
