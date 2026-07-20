import importlib.util
import os
import sys
import unittest
from unittest import mock


AGENT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent")
sys.path.insert(0, AGENT_DIR)
SPEC = importlib.util.spec_from_file_location(
    "eyes_agent_module", os.path.join(AGENT_DIR, "eyes-agent.py")
)
EYES_AGENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EYES_AGENT)


class AgentWireGuardTest(unittest.TestCase):
    def test_wireguard_dump_omits_keys_and_keeps_peer_health_fields(self):
        dump = (
            "dev_wg\tprivate\tpublic\t51820\toff\n"
            "dev_wg\tpeer-public\t(none)\t198.51.100.1:51820\t10.0.1.1/32\t100\t20\t30\t25\n"
        )
        completed = mock.Mock(returncode=0, stdout=dump, stderr="")
        with mock.patch.object(EYES_AGENT.shutil, "which", return_value="/usr/bin/wg"):
            with mock.patch.object(EYES_AGENT.subprocess, "run", return_value=completed):
                result = EYES_AGENT.get_wireguard_status()

        self.assertEqual(result[0]["name"], "dev_wg")
        self.assertEqual(result[0]["peers"][0]["allowed_ips"], "10.0.1.1/32")
        self.assertEqual(result[0]["peers"][0]["latest_handshake"], 100)
        self.assertNotIn("private", str(result))
        self.assertNotIn("peer-public", str(result))


if __name__ == "__main__":
    unittest.main()
