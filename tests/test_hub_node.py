import os
import tempfile
import unittest
from unittest import mock

import models
from fleet import get_node, init_fleet_db
from hub_node import refresh_local_hub_node


class HubNodeObserverTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "eyes-hub-node-test.db")
        self.db_patch = mock.patch.object(models, "DB_PATH", self.db_path)
        self.db_patch.start()
        models.init_db()
        init_fleet_db()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_refresh_publishes_heartbeat_inventory_and_resources(self):
        with mock.patch.dict(
            os.environ,
            {"EYES_HUB_NODE_ID": "hub-test", "EYES_HUB_DISPLAY_NAME": "Test Hub"},
        ):
            self.assertEqual(refresh_local_hub_node(), "hub-test")

        node = get_node("hub-test")
        self.assertEqual(node["display_name"], "Test Hub")
        self.assertEqual(node["status"], "ready")
        self.assertEqual(node["connection_status"], "online")
        self.assertEqual(node["labels"]["eyes.io/source"], "hub-runtime")
        self.assertIn("inventory", node["snapshots"])
        self.assertIn("resources", node["snapshots"])
        capabilities = node["snapshots"]["inventory"]["payload"]["capabilities"]
        self.assertTrue(any(item["name"] == "eyes.io/control-plane.hub" for item in capabilities))


if __name__ == "__main__":
    unittest.main()
