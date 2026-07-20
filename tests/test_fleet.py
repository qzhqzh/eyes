import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import models
from fleet import (
    ConflictError,
    acknowledge_command,
    authenticate_node,
    create_workload,
    enqueue_command,
    enroll_node,
    ensure_local_hub_node,
    get_fleet_summary,
    get_commands,
    get_node,
    init_fleet_db,
    list_nodes,
    list_workloads,
    put_snapshot,
    record_heartbeat,
)


class FleetStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "eyes-test.db")
        self.db_patch = mock.patch.object(models, "DB_PATH", self.db_path)
        self.db_patch.start()
        models.init_db()
        init_fleet_db()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_enroll_heartbeat_and_snapshot_are_persisted(self):
        token = enroll_node(
            {
                "node_id": "node-1",
                "hostname": "worker-1",
                "display_name": "GPU Worker",
                "roles": ["gpu-worker"],
                "labels": {"eyes.io/site": "home"},
                "agent_version": "0.2.0",
                "protocol_version": "eyes.node.v1",
            }
        )

        self.assertTrue(authenticate_node("node-1", token))
        self.assertFalse(authenticate_node("node-1", "wrong-token"))
        with self.assertRaises(ConflictError):
            enroll_node({"node_id": "node-1", "hostname": "impostor"})

        record_heartbeat(
            "node-1",
            {
                "boot_id": "boot-a",
                "sequence": 3,
                "agent_version": "0.2.0",
                "protocol_version": "eyes.node.v1",
            },
        )
        result = put_snapshot(
            "node-1",
            "resources",
            1,
            {"cpu": {"capacity": 8}, "memory": {"capacity_bytes": 1024}},
            "2026-07-20T00:00:00Z",
        )
        duplicate = put_snapshot(
            "node-1",
            "resources",
            1,
            {"cpu": {"capacity": 8}, "memory": {"capacity_bytes": 1024}},
            "2026-07-20T00:00:00Z",
        )

        self.assertFalse(result["unchanged"])
        self.assertTrue(duplicate["unchanged"])
        node = get_node("node-1")
        self.assertEqual(node["status"], "ready")
        self.assertEqual(node["last_sequence"], 3)
        self.assertEqual(node["roles"], ["gpu-worker"])
        self.assertEqual(node["snapshots"]["resources"]["generation"], 1)

    def test_stale_heartbeat_and_conflicting_snapshot_are_rejected(self):
        enroll_node({"node_id": "node-2", "hostname": "worker-2"})
        with self.assertRaises(ValueError):
            record_heartbeat("node-2", {"boot_id": "", "sequence": 1})
        with self.assertRaises(ValueError):
            record_heartbeat("node-2", {"boot_id": "boot-a", "sequence": 0})
        record_heartbeat("node-2", {"boot_id": "boot-a", "sequence": 5})
        with self.assertRaises(ConflictError):
            record_heartbeat("node-2", {"boot_id": "boot-a", "sequence": 4})

        put_snapshot("node-2", "inventory", 1, {"hostname": "worker-2"})
        with self.assertRaises(ConflictError):
            put_snapshot("node-2", "inventory", 1, {"hostname": "changed"})

        record_heartbeat("node-2", {"boot_id": "boot-b", "sequence": 1})
        self.assertEqual(get_node("node-2")["last_sequence"], 1)

    def test_hub_node_and_workload_control_plane_tables(self):
        with mock.patch.dict(os.environ, {"EYES_HUB_NODE_ID": "hub-test"}):
            self.assertEqual(ensure_local_hub_node(), "hub-test")
        with self.assertRaises(ConflictError):
            enroll_node({"node_id": "hub-test", "hostname": "impostor"})
        nodes = list_nodes()
        self.assertEqual(nodes[0]["roles"], ["hub"])

        workload_id = create_workload(
            "example",
            {"type": "batch", "resources": {"requests": {"cpu_millis": 500}}},
            "test-user",
        )
        workloads = list_workloads()
        self.assertEqual(workloads[0]["id"], workload_id)
        self.assertEqual(workloads[0]["status"], "pending")

    def test_connectivity_and_summary_only_include_online_resources(self):
        enroll_node({"node_id": "node-online", "hostname": "online-worker"})
        record_heartbeat("node-online", {"boot_id": "boot-online", "sequence": 1})
        put_snapshot(
            "node-online",
            "resources",
            1,
            {
                "cpu": {"capacity_millis": 4000, "allocatable_millis": 3000},
                "memory": {
                    "capacity_bytes": 8000,
                    "allocatable_bytes": 7000,
                    "available_bytes": 6000,
                },
                "filesystem": {"root": {"capacity_bytes": 10000, "available_bytes": 4000}},
            },
        )
        put_snapshot(
            "node-online",
            "inventory",
            1,
            {"capabilities": [{"name": "eyes.io/test", "health": "ready"}]},
        )

        node = get_node("node-online")
        self.assertEqual(node["connection_status"], "online")
        summary = get_fleet_summary()
        self.assertEqual(summary["connection_counts"]["online"], 1)
        self.assertEqual(summary["resource_node_count"], 1)
        self.assertEqual(summary["resources"]["cpu_capacity_millis"], 4000)
        self.assertEqual(summary["resources"]["memory_available_bytes"], 6000)
        self.assertEqual(summary["capabilities"], {"eyes.io/test": 1})

        conn = models.get_db()
        old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        conn.execute("UPDATE nodes SET last_seen_at = ? WHERE id = ?", (old, "node-online"))
        conn.commit()
        conn.close()
        self.assertEqual(get_node("node-online")["connection_status"], "offline")
        offline_summary = get_fleet_summary()
        self.assertEqual(offline_summary["resource_node_count"], 0)
        self.assertEqual(offline_summary["resources"]["cpu_capacity_millis"], 0)

    def test_commands_expire_and_terminal_ack_cannot_regress(self):
        enroll_node({"node_id": "node-command", "hostname": "command-worker"})
        now = datetime.now(timezone.utc)
        enqueue_command(
            "node-command",
            "observe",
            {},
            expires_at=(now - timedelta(seconds=1)).isoformat(),
        )
        command_id = enqueue_command(
            "node-command",
            "observe",
            {"scope": "system"},
            expires_at=(now + timedelta(minutes=1)).isoformat(),
        )

        commands = get_commands("node-command")
        self.assertEqual([item["command_id"] for item in commands["commands"]], [command_id])

        acknowledge_command("node-command", command_id, "succeeded", {"ok": True})
        acknowledge_command("node-command", command_id, "succeeded", {"ok": True})
        with self.assertRaises(ConflictError):
            acknowledge_command("node-command", command_id, "accepted")

    def test_sqlite_foreign_keys_are_enabled(self):
        conn = models.get_db()
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        conn.close()
        with self.assertRaises(sqlite3.IntegrityError):
            enqueue_command("missing-node", "observe", {})

        item_id = models.add_check_item("http", "legacy-check", "http://localhost")
        models.save_check_result(item_id, "http", "legacy-check", True, "ok")
        models.delete_check_item(item_id)
        self.assertEqual(models.get_check_results(), [])


if __name__ == "__main__":
    unittest.main()
