import os
import tempfile
import unittest

from network_status import (
    collect_wireguard_status,
    merge_agent_wireguard_status,
    mounted_filesystem_type,
    probe_wireguard_reachability,
)


class NetworkStatusTest(unittest.TestCase):
    def test_mount_type_requires_an_explicit_mount_point(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            mountinfo = os.path.join(temp_dir, "mountinfo")
            with open(mountinfo, "w", encoding="utf-8") as handle:
                handle.write("42 31 0:51 / /mnt/nas ro - cifs //nas/share rw\n")
                handle.write("43 31 8:1 / /data rw - ext4 /dev/sda1 rw\n")

            self.assertEqual(mounted_filesystem_type("/mnt/nas", mountinfo), "cifs")
            self.assertIsNone(mounted_filesystem_type("/mnt/nas/missing", mountinfo))

    def test_host_interfaces_are_used_even_when_container_proc_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            host_path = os.path.join(temp_dir, "host-dev")
            container_path = os.path.join(temp_dir, "container-dev")
            with open(host_path, "w", encoding="utf-8") as handle:
                handle.write("wg0: 10 0 0 0 0 0 0 0 20 0 0 0 0 0 0 0\n")
                handle.write("dev_wg: 30 0 0 0 0 0 0 0 40 0 0 0 0 0 0 0\n")
            with open(container_path, "w", encoding="utf-8") as handle:
                handle.write("eth0: 1 0 0 0 0 0 0 0 2 0 0 0 0 0 0 0\n")

            status = collect_wireguard_status((host_path, container_path))

        self.assertTrue(status["wg0"]["ok"])
        self.assertEqual(status["wg0"]["rx_bytes"], 10)
        self.assertEqual(status["wg0"]["tx_bytes"], 20)
        self.assertTrue(status["wg1"]["ok"])
        self.assertEqual(status["wg1"]["rx_bytes"], 30)

    def test_peer_handshake_distinguishes_interface_from_node_health(self):
        status = {
            "wg0": {"ok": True, "rx_bytes": 10, "tx_bytes": 20, "ip": None},
            "wg1": {"ok": True, "rx_bytes": 30, "tx_bytes": 40, "ip": None},
        }
        interfaces = [
            {"name": "wg0", "peers": [{"allowed_ips": "10.0.0.2/32", "latest_handshake": 990}]},
            {"name": "dev_wg", "peers": [{"allowed_ips": "10.0.1.1/32", "latest_handshake": 100}]},
        ]

        merged = merge_agent_wireguard_status(status, interfaces, now=1000, fresh_seconds=180)

        self.assertTrue(merged["wg0"]["ok"])
        self.assertTrue(merged["wg0"]["peer_online"])
        self.assertFalse(merged["wg1"]["ok"])
        self.assertTrue(merged["wg1"]["interface_up"])
        self.assertFalse(merged["wg1"]["peer_online"])
        self.assertEqual(merged["wg1"]["peers"][0]["handshake_age_seconds"], 900)

    def test_configured_peer_does_not_inherit_another_peers_handshake(self):
        status = {
            "wg0": {"ok": False, "rx_bytes": 0, "tx_bytes": 0, "ip": None},
            "wg1": {"ok": True, "rx_bytes": 0, "tx_bytes": 0, "ip": None},
        }
        interfaces = [{
            "name": "dev_wg",
            "peers": [{"allowed_ips": "10.0.1.9/32", "latest_handshake": 990}],
        }]

        merged = merge_agent_wireguard_status(
            status, interfaces, now=1000, fresh_seconds=180,
            probes={"wg1": "10.0.1.1"},
        )

        self.assertFalse(merged["wg0"]["ok"])
        self.assertFalse(merged["wg0"]["interface_up"])
        self.assertFalse(merged["wg1"]["ok"])
        self.assertEqual(merged["wg1"]["peers"], [])

    def test_reachability_fallback_marks_offline_peer_down(self):
        status = {
            "wg0": {"ok": True, "rx_bytes": 0, "tx_bytes": 0, "ip": None},
            "wg1": {"ok": True, "rx_bytes": 0, "tx_bytes": 0, "ip": None},
        }

        class Response:
            def __init__(self, returncode):
                self.returncode = returncode

        def runner(command, **_kwargs):
            return Response(0 if command[-1] == "10.0.0.250" else 1)

        probed = probe_wireguard_reachability(
            status, {"wg0": "10.0.0.250", "wg1": "10.0.1.1"}, runner
        )

        self.assertTrue(probed["wg0"]["ok"])
        self.assertFalse(probed["wg1"]["ok"])
        self.assertEqual(probed["wg1"]["peers"][0]["status_source"], "reachability")
