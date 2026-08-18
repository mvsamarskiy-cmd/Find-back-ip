from unittest import TestCase
from unittest.mock import patch

from verification import instagram_live


class InstagramLiveTests(TestCase):
    def test_exact_meta_exists_promotes_to_taken(self):
        legacy = {"status": "unknown", "source": "public_web"}
        evidence = {
            "signal": "exists",
            "confidence": 0.95,
            "detail": "exact profile",
        }
        with patch.object(instagram_live.meta_instagram_oembed_adapter, "check_username", return_value=evidence):
            row = instagram_live.enrich_instagram("natgeo", legacy)
        self.assertEqual(row["status"], "taken")
        self.assertEqual(row["source"], "meta_instagram_oembed")
        self.assertEqual(row["claimability"], "not_claimable")

    def test_unknown_meta_result_keeps_legacy(self):
        legacy = {"status": "not_found", "source": "public_web"}
        evidence = {"signal": "unknown", "confidence": 0.0, "detail": "404"}
        with patch.object(instagram_live.meta_instagram_oembed_adapter, "check_username", return_value=evidence):
            row = instagram_live.enrich_instagram("rarehandle", legacy)
        self.assertIs(row, legacy)

    def test_rate_limit_keeps_legacy(self):
        legacy = {"status": "unknown", "source": "public_web"}
        evidence = {"signal": "rate_limited", "confidence": 0.0, "detail": "429"}
        with patch.object(instagram_live.meta_instagram_oembed_adapter, "check_username", return_value=evidence):
            row = instagram_live.enrich_instagram("example", legacy)
        self.assertIs(row, legacy)

    def test_existing_legacy_taken_skips_meta_probe(self):
        legacy = {"status": "taken", "source": "public_web"}
        with patch.object(instagram_live.meta_instagram_oembed_adapter, "check_username") as probe:
            row = instagram_live.enrich_instagram("nike", legacy)
        self.assertIs(row, legacy)
        probe.assert_not_called()
