import os
import tempfile
import unittest

from network_status import collect_wireguard_status, mounted_filesystem_type


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
