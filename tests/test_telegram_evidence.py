import unittest
from types import SimpleNamespace
from unittest.mock import patch

import availability
import telegram_evidence
import telegram_integration


def response(status_code, payload=None):
    value = SimpleNamespace(status_code=status_code)
    value.json = lambda: payload
    return value


class TelegramEvidenceTransportTests(unittest.TestCase):
    @patch.dict("telegram_evidence.os.environ", {}, clear=True)
    def test_unconfigured_service_returns_none(self):
        self.assertIsNone(telegram_evidence.fetch_telegram_evidence("Example"))

    @patch.dict(
        "telegram_evidence.os.environ",
        {"TELEGRAM_EVIDENCE_URL": "http://internal.test", "TELEGRAM_EVIDENCE_TOKEN": "secret"},
        clear=True,
    )
    def test_service_requires_https(self):
        result = telegram_evidence.fetch_telegram_evidence("Example")
        self.assertEqual(result["transport_status"], "configuration_error")

    @patch.dict(
        "telegram_evidence.os.environ",
        {"TELEGRAM_EVIDENCE_URL": "https://telegram-evidence.test", "TELEGRAM_EVIDENCE_TOKEN": "secret"},
        clear=True,
    )
    @patch("telegram_evidence.requests.get")
    def test_valid_payload_is_normalized(self, get):
        get.return_value = response(200, {
            "username": "@Example",
            "mtproto": {"status": "not_found", "detail": "No peer"},
            "fragment": {
                "status": "for_sale",
                "detail": "Auction listing",
                "url": "https://fragment.com/username/example",
                "price": 1500,
                "currency": "ton",
            },
        })
        result = telegram_evidence.fetch_telegram_evidence("Example")
        self.assertEqual(result["transport_status"], "ok")
        self.assertEqual(result["evidence"]["username"], "example")
        self.assertEqual(result["evidence"]["fragment"]["currency"], "TON")
        self.assertNotIn("secret", str(result))

    @patch.dict(
        "telegram_evidence.os.environ",
        {"TELEGRAM_EVIDENCE_URL": "https://telegram-evidence.test", "TELEGRAM_EVIDENCE_TOKEN": "secret"},
        clear=True,
    )
    @patch("telegram_evidence.requests.get", return_value=response(429))
    def test_rate_limit_is_explicit(self, _get):
        result = telegram_evidence.fetch_telegram_evidence("Example")
        self.assertEqual(result["transport_status"], "rate_limited")

    @patch.dict(
        "telegram_evidence.os.environ",
        {"TELEGRAM_EVIDENCE_URL": "https://telegram-evidence.test", "TELEGRAM_EVIDENCE_TOKEN": "secret"},
        clear=True,
    )
    @patch("telegram_evidence.requests.get")
    def test_mismatched_username_is_malformed(self, get):
        get.return_value = response(200, {
            "username": "other",
            "mtproto": {"status": "not_found"},
            "fragment": {"status": "not_found"},
        })
        result = telegram_evidence.fetch_telegram_evidence("Example")
        self.assertEqual(result["transport_status"], "malformed")


class TelegramClassificationTests(unittest.TestCase):
    def envelope(self, mtproto, fragment, **fragment_fields):
        return {
            "transport_status": "ok",
            "evidence": {
                "username": "example",
                "mtproto": {"status": mtproto, "detail": "mtproto"},
                "fragment": {
                    "status": fragment,
                    "detail": "fragment",
                    "url": "https://fragment.com/username/example",
                    **fragment_fields,
                },
            },
        }

    def test_fragment_sale_is_purchasable(self):
        result = telegram_integration.classify_telegram_evidence(
            "Example",
            self.envelope("occupied", "for_sale", price=420, currency="TON"),
        )
        self.assertEqual(result["status"], "purchasable")
        self.assertEqual(result["source"], "telegram_evidence_service")
        self.assertEqual(result["offer"]["provider"], "fragment")
        self.assertEqual(result["offer"]["purchase_price"], 420)
        self.assertEqual(result["offer"]["currency"], "TON")

    def test_mtproto_occupied_is_taken(self):
        result = telegram_integration.classify_telegram_evidence(
            "Example", self.envelope("occupied", "not_found")
        )
        self.assertEqual(result["status"], "taken")
        self.assertEqual(result["claimability"], "not_claimable")

    def test_reserved_is_reserved(self):
        result = telegram_integration.classify_telegram_evidence(
            "Example", self.envelope("reserved", "not_found")
        )
        self.assertEqual(result["status"], "reserved")

    def test_two_not_found_observations_never_claim_free(self):
        result = telegram_integration.classify_telegram_evidence(
            "Example", self.envelope("not_found", "not_found")
        )
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["claimability"], "unconfirmed")
        self.assertNotEqual(result["status"], "claimable")

    def test_service_failure_does_not_fall_back_to_public_web(self):
        result = telegram_integration.classify_telegram_evidence(
            "Example", {"transport_status": "auth_error", "detail": "auth failed"}
        )
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["source"], "telegram_evidence_service")

    @patch("telegram_integration.fetch_telegram_evidence", return_value=None)
    @patch.object(telegram_integration, "_PUBLIC_CHECKER", return_value={"status": "not_found"})
    def test_public_fallback_only_when_service_unconfigured(self, public_checker, _fetch):
        self.assertEqual(telegram_integration.check_telegram("Example")["status"], "not_found")
        public_checker.assert_called_once_with("Example")

    def test_install_replaces_availability_checker(self):
        original = availability.check_telegram
        try:
            telegram_integration._INSTALLED = False
            telegram_integration.install()
            self.assertIs(availability.check_telegram, telegram_integration.check_telegram)
        finally:
            availability.check_telegram = original
            telegram_integration._INSTALLED = False


if __name__ == "__main__":
    unittest.main()
