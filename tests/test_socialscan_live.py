import os
from unittest import TestCase
from unittest.mock import patch

import availability
from verification import socialscan_live


class SocialscanLiveTests(TestCase):
    def setUp(self):
        self.original = availability.check_x
        socialscan_live._ORIGINAL_X = self.original

    def tearDown(self):
        availability.check_x = self.original
        socialscan_live._ORIGINAL_X = self.original
        socialscan_live._INSTALLED = False

    def test_occupied_socialscan_signal_promotes_to_taken(self):
        evidence = {
            "signal": "exists",
            "confidence": 0.9,
            "detail": "occupied",
        }
        with patch.object(socialscan_live.socialscan_adapter, "check_username", return_value=evidence):
            with patch.dict(os.environ, {}, clear=True):
                row = socialscan_live.check_x("drity")
        self.assertEqual(row["status"], "taken")
        self.assertEqual(row["source"], "socialscan")
        self.assertEqual(row["claimability"], "not_claimable")

    def test_available_socialscan_signal_is_not_verified_claimable(self):
        evidence = {
            "signal": "claimable",
            "confidence": 0.86,
            "detail": "available",
        }
        with patch.object(socialscan_live.socialscan_adapter, "check_username", return_value=evidence):
            with patch.dict(os.environ, {}, clear=True):
                row = socialscan_live.check_x("rarehandle")
        self.assertEqual(row["status"], "not_found")
        self.assertEqual(row["claimability"], "unconfirmed")
        self.assertNotEqual(row["status"], "claimable")

    def test_official_x_api_path_keeps_priority(self):
        official = {"status": "taken", "source": "x_api"}
        with patch.dict(os.environ, {"X_BEARER_TOKEN": "configured"}, clear=True):
            with patch.object(socialscan_live, "_ORIGINAL_X", return_value=official) as original:
                with patch.object(socialscan_live.socialscan_adapter, "check_username") as socialscan:
                    row = socialscan_live.check_x("example")
        self.assertEqual(row, official)
        original.assert_called_once_with("example")
        socialscan.assert_not_called()

    def test_unknown_socialscan_signal_falls_back_to_public_checker(self):
        fallback = {"status": "unknown", "source": "public_web"}
        evidence = {"signal": "unknown", "confidence": 0.0, "detail": "blocked"}
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(socialscan_live, "_ORIGINAL_X", return_value=fallback) as original:
                with patch.object(socialscan_live.socialscan_adapter, "check_username", return_value=evidence):
                    row = socialscan_live.check_x("example")
        self.assertEqual(row, fallback)
        original.assert_called_once_with("example")

    def test_install_is_idempotent(self):
        socialscan_live._INSTALLED = False
        socialscan_live._ORIGINAL_X = None
        socialscan_live.install()
        installed = availability.check_x
        socialscan_live.install()
        self.assertIs(availability.check_x, installed)
