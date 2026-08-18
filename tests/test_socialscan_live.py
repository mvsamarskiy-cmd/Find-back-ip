import os
from unittest import TestCase
from unittest.mock import patch

from verification import socialscan_live


class SocialscanLiveTests(TestCase):
    def test_occupied_socialscan_signal_promotes_to_taken(self):
        evidence = {
            "signal": "exists",
            "confidence": 0.9,
            "detail": "occupied",
        }
        legacy = {"status": "unknown", "source": "public_web"}
        with patch.object(socialscan_live.socialscan_adapter, "check_username", return_value=evidence):
            with patch.dict(os.environ, {}, clear=True):
                row = socialscan_live.enrich_x("drity", legacy)
        self.assertEqual(row["status"], "taken")
        self.assertEqual(row["source"], "socialscan")
        self.assertEqual(row["claimability"], "not_claimable")

    def test_available_socialscan_signal_is_not_verified_claimable(self):
        evidence = {
            "signal": "claimable",
            "confidence": 0.86,
            "detail": "available",
        }
        legacy = {"status": "not_found", "source": "public_web"}
        with patch.object(socialscan_live.socialscan_adapter, "check_username", return_value=evidence):
            with patch.dict(os.environ, {}, clear=True):
                row = socialscan_live.enrich_x("rarehandle", legacy)
        self.assertEqual(row["status"], "not_found")
        self.assertEqual(row["claimability"], "unconfirmed")
        self.assertNotEqual(row["status"], "claimable")

    def test_official_x_api_path_keeps_priority(self):
        official = {"status": "taken", "source": "x_api"}
        with patch.dict(os.environ, {"X_BEARER_TOKEN": "configured"}, clear=True):
            with patch.object(socialscan_live.socialscan_adapter, "check_username") as socialscan:
                row = socialscan_live.enrich_x("example", official)
        self.assertEqual(row, official)
        socialscan.assert_not_called()

    def test_unknown_socialscan_signal_keeps_legacy_result(self):
        legacy = {"status": "unknown", "source": "public_web"}
        evidence = {"signal": "unknown", "confidence": 0.0, "detail": "blocked"}
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(socialscan_live.socialscan_adapter, "check_username", return_value=evidence):
                row = socialscan_live.enrich_x("example", legacy)
        self.assertIs(row, legacy)

    def test_socialscan_never_weakens_existing_taken_evidence(self):
        legacy = {"status": "taken", "source": "public_web"}
        evidence = {"signal": "claimable", "confidence": 0.86, "detail": "available"}
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(socialscan_live.socialscan_adapter, "check_username", return_value=evidence):
                row = socialscan_live.enrich_x("example", legacy)
        self.assertIs(row, legacy)
