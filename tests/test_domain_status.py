import os
import tempfile
import unittest
from unittest import mock
import urllib.error

from domain_status import collect_domain_status, discover_domains, probe_domain


class DomainStatusTest(unittest.TestCase):
    def test_discovers_unique_domains_and_upstreams(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(os.path.join(temp_dir, "site.conf"), "w", encoding="utf-8") as handle:
                handle.write("server { server_name one.example.com two.example.com; proxy_pass http://127.0.0.1:8000; }")
            with open(os.path.join(temp_dir, "catchall.conf"), "w", encoding="utf-8") as handle:
                handle.write("server { server_name _; return 404; }")
            domains = discover_domains(temp_dir)

        self.assertEqual([item["domain"] for item in domains], ["one.example.com", "two.example.com"])
        self.assertEqual(domains[0]["upstreams"], ["http://127.0.0.1:8000"])

    def test_http_404_is_reachable_but_distinct(self):
        error = urllib.error.HTTPError("https://one.example.com", 404, "not found", {}, None)
        opener = mock.Mock()
        opener.open.side_effect = error
        with mock.patch("domain_status.urllib.request.build_opener", return_value=opener):
            result = probe_domain("one.example.com")

        self.assertTrue(result["reachable"])
        self.assertEqual(result["state"], "not_found")
        self.assertEqual(result["status_code"], 404)

    def test_only_configured_domain_can_be_probed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(os.path.join(temp_dir, "site.conf"), "w", encoding="utf-8") as handle:
                handle.write("server { server_name one.example.com; }")
            with mock.patch("domain_status.probe_domain") as probe:
                result = collect_domain_status(temp_dir, only_domain="outside.example.com")

        self.assertEqual(result, [])
        probe.assert_not_called()

    def test_upstreams_are_scoped_to_their_server_block(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(os.path.join(temp_dir, "sites.conf"), "w", encoding="utf-8") as handle:
                handle.write(
                    "server { server_name one.example.com; location / { proxy_pass http://one:80; } }"
                    "server { server_name two.example.com; location / { proxy_pass http://two:80; } }"
                )
            domains = discover_domains(temp_dir)

        self.assertEqual(domains[0]["upstreams"], ["http://one:80"])
        self.assertEqual(domains[1]["upstreams"], ["http://two:80"])


if __name__ == "__main__":
    unittest.main()
