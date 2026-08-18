import unittest
from types import SimpleNamespace
from unittest.mock import patch

from verification.no_key_ensemble import verify_no_key
from verification.providers import maigret_adapter, whatsmyname_adapter


class FakeResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


class NoKeyProviderAdapterTests(unittest.TestCase):
    def test_whatsmyname_existing_fingerprint_is_exists(self):
        dataset = {
            "sites": [{
                "name": "Instagram",
                "uri_check": "https://example.test/{account}",
                "e_code": 200,
                "e_string": "PROFILE",
                "m_code": 404,
                "m_string": "MISSING",
                "known": ["known"],
                "cat": "social",
            }]
        }

        def requester(method, url, **kwargs):
            return FakeResponse(200, "PROFILE")

        row = whatsmyname_adapter.check_username(
            "known", "instagram", dataset=dataset, requester=requester
        )
        self.assertEqual(row["signal"], "exists")
        self.assertEqual(row["source"], "whatsmyname")

    def test_whatsmyname_missing_is_only_absent_not_claimable(self):
        dataset = {
            "sites": [{
                "name": "Instagram",
                "uri_check": "https://example.test/{account}",
                "e_code": 200,
                "e_string": "PROFILE",
                "m_code": 404,
                "m_string": "MISSING",
                "known": ["known"],
                "cat": "social",
            }]
        }

        def requester(method, url, **kwargs):
            return FakeResponse(404, "MISSING")

        row = whatsmyname_adapter.check_username(
            "rarehandle", "instagram", dataset=dataset, requester=requester
        )
        self.assertEqual(row["signal"], "absent")
        self.assertNotEqual(row["signal"], "claimable")

    def test_maigret_hit_parser_only_uses_target_platform(self):
        payload = {
            "Instagram": {"status": "claimed", "url": "https://instagram.com/example"},
            "GitHub": {"status": "claimed", "url": "https://github.com/example"},
        }
        hits = maigret_adapter._extract_hits(payload, "instagram")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["site"], "Instagram")

    def test_no_key_ensemble_conflict_beats_absence(self):
        def socialscan(handle, platform):
            return {"signal": "absent", "source": "socialscan", "confidence": 0.7}

        def wmn(handle, platform):
            return {"signal": "exists", "source": "whatsmyname", "confidence": 0.84}

        with patch("verification.no_key_ensemble.PROVIDERS", {
            "socialscan": socialscan,
            "whatsmyname": wmn,
        }):
            verdict = verify_no_key("example", "instagram", ["socialscan", "whatsmyname"])
        self.assertEqual(verdict["verdict"], "taken")

    def test_maigret_missing_dependency_fails_closed(self):
        with patch("verification.providers.maigret_adapter.available", return_value=False):
            row = maigret_adapter.check_username("example", "instagram")
        self.assertEqual(row["signal"], "unknown")


if __name__ == "__main__":
    unittest.main()
