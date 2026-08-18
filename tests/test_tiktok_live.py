from unittest import TestCase
from unittest.mock import patch

from verification import tiktok_live


class TikTokLiveTests(TestCase):
    def test_exact_positive_evidence_promotes_to_taken(self):
        legacy = {"status": "unknown", "source": "public_web"}
        evidence = {
            "signal": "exists",
            "confidence": 0.97,
            "detail": "exact profile",
        }
        with patch.object(tiktok_live.tiktok_oembed_adapter, "check_username", return_value=evidence):
            row = tiktok_live.enrich_tiktok("mazomoto", legacy)
        self.assertEqual(row["status"], "taken")
        self.assertEqual(row["source"], "tiktok_oembed")
        self.assertEqual(row["claimability"], "not_claimable")

    def test_non_positive_evidence_preserves_legacy_result(self):
        legacy = {"status": "not_found", "source": "public_web"}
        evidence = {"signal": "unknown", "confidence": 0.0, "detail": "404"}
        with patch.object(tiktok_live.tiktok_oembed_adapter, "check_username", return_value=evidence):
            row = tiktok_live.enrich_tiktok("rarehandle", legacy)
        self.assertIs(row, legacy)

    def test_existing_taken_is_not_rechecked(self):
        legacy = {"status": "taken", "source": "public_web"}
        with patch.object(tiktok_live.tiktok_oembed_adapter, "check_username") as probe:
            row = tiktok_live.enrich_tiktok("mazomoto", legacy)
        self.assertIs(row, legacy)
        probe.assert_not_called()
