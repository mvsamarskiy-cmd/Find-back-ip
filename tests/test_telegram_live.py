import unittest
from unittest.mock import patch

from verification import telegram_live


LEGACY_UNKNOWN = {
    "status": "unknown",
    "detail": "inconclusive",
    "url": "https://t.me/example",
    "source": "public_web",
    "method": "public_profile",
    "confidence": 0.0,
    "occupancy": "unknown",
    "claimability": "unconfirmed",
}


class TelegramLiveTests(unittest.TestCase):
    def test_fragment_taken_promotes_to_taken(self):
        with patch.object(telegram_live.fragment_username_adapter, "check_username", return_value={
            "signal": "exists", "confidence": 0.95, "detail": "Taken"
        }):
            result = telegram_live.enrich_telegram("durov", dict(LEGACY_UNKNOWN))
        self.assertEqual(result["status"], "taken")
        self.assertEqual(result["source"], "fragment_public_web")

    def test_fragment_marketplace_available_is_reserved_not_green(self):
        with patch.object(telegram_live.fragment_username_adapter, "check_username", return_value={
            "signal": "purchasable", "confidence": 0.9, "detail": "Marketplace available"
        }):
            result = telegram_live.enrich_telegram("premiumname", dict(LEGACY_UNKNOWN))
        self.assertEqual(result["status"], "reserved")
        self.assertNotIn(result["status"], {"claimable", "purchasable"})

    def test_whatsmyname_positive_promotes_to_taken(self):
        with patch.object(telegram_live.fragment_username_adapter, "check_username", return_value={"signal": "unknown"}):
            with patch.object(telegram_live.whatsmyname_adapter, "check_username", return_value={
                "signal": "exists", "confidence": 0.84, "detail": "Existing account"
            }):
                result = telegram_live.enrich_telegram("telegram", dict(LEGACY_UNKNOWN))
        self.assertEqual(result["status"], "taken")
        self.assertEqual(result["source"], "whatsmyname")

    def test_whatsmyname_absent_is_ignored(self):
        with patch.object(telegram_live.fragment_username_adapter, "check_username", return_value={"signal": "unknown"}):
            with patch.object(telegram_live.whatsmyname_adapter, "check_username", return_value={
                "signal": "absent", "confidence": 0.68, "detail": "Missing"
            }):
                result = telegram_live.enrich_telegram("mazomoto", dict(LEGACY_UNKNOWN))
        self.assertEqual(result, LEGACY_UNKNOWN)

    def test_existing_legacy_taken_skips_secondary_calls(self):
        row = dict(LEGACY_UNKNOWN)
        row["status"] = "taken"
        with patch.object(telegram_live.fragment_username_adapter, "check_username") as fragment:
            result = telegram_live.enrich_telegram("telegram", row)
        self.assertEqual(result, row)
        fragment.assert_not_called()


if __name__ == "__main__":
    unittest.main()
