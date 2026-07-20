import unittest
from unittest import mock

import checker


class GroupedCheckerTest(unittest.TestCase):
    def test_agent_url_environment_override_preserves_upgrade_compatibility(self):
        with mock.patch.dict("os.environ", {"EYES_AGENT_URL": "http://127.0.0.1:9091"}):
            self.assertEqual(checker._get_agent_url(), "http://127.0.0.1:9091")

    def test_agent_inventory_is_fetched_once_per_group(self):
        items = [
            {"id": 1, "type": "systemd", "name": "SSH", "target": "ssh.service", "enabled": 1},
            {"id": 2, "type": "systemd", "name": "Cron", "target": "cron.service", "enabled": 1},
            {"id": 3, "type": "crond", "name": "Backup", "target": "/opt/backup", "enabled": 1},
            {"id": 4, "type": "crond", "name": "Report", "target": "/opt/report", "enabled": 1},
        ]

        def response(endpoint):
            if endpoint == "/api/systemd":
                return [{"name": "ssh", "active": "active"}, {"name": "cron", "active": "active"}]
            return {"root": ["0 1 * * * /opt/backup", "0 2 * * * /opt/report"]}

        with mock.patch.object(checker, "_query_agent_api", side_effect=response) as query:
            results = checker.run_all_checks(items)

        self.assertTrue(all(result["ok"] for result in results))
        self.assertEqual(query.call_count, 2)
        query.assert_has_calls([mock.call("/api/systemd"), mock.call("/api/crontab")])


if __name__ == "__main__":
    unittest.main()
