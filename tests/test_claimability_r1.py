import unittest
from pathlib import Path
from unittest.mock import patch

import telegram_evidence
import telegram_integration
from verification.diagnostics import provider_diagnostics


class TelegramStrictClaimabilityTests(unittest.TestCase):
    def envelope(self, claim_status=None, *, mtproto="not_found", fragment="not_found", method="account.checkUsername"):
        evidence = {
            "username": "example",
            "mtproto": {"status": mtproto, "detail": "mt"},
            "fragment": {
                "status": fragment,
                "detail": "fragment",
                "url": "https://fragment.com/username/example",
            },
        }
        if claim_status is not None:
            evidence["claimability"] = {
                "status": claim_status,
                "method": method,
                "scope": "account",
                "detail": "direct Telegram check",
            }
        return {"transport_status": "ok", "evidence": evidence}

    def test_contract_normalizes_authoritative_claimability(self):
        payload = {
            "username": "@Example",
            "mtproto": {"status": "not_found"},
            "fragment": {"status": "not_found"},
            "claimability": {
                "status": "claimable",
                "method": "account.checkUsername",
                "scope": "account",
                "detail": "available",
            },
        }
        result = telegram_evidence._normalize_payload(payload, "example")
        self.assertEqual(result["claimability"]["status"], "claimable")
        self.assertEqual(result["claimability"]["method"], "account.checkUsername")

    def test_contract_rejects_unknown_claimability_method(self):
        payload = {
            "username": "example",
            "mtproto": {"status": "not_found"},
            "fragment": {"status": "not_found"},
            "claimability": {
                "status": "claimable",
                "method": "contacts.resolveUsername",
                "scope": "account",
            },
        }
        with self.assertRaisesRegex(ValueError, "claimability method"):
            telegram_evidence._normalize_payload(payload, "example")

    def test_direct_checkusername_success_is_strict_claimable(self):
        result = telegram_integration.classify_telegram_evidence(
            "Example", self.envelope("claimable")
        )
        self.assertEqual(result["status"], "claimable")
        self.assertEqual(result["claimability"], "confirmed")
        self.assertEqual(result["method"], "account.checkUsername")

    def test_claimable_conflicting_with_fragment_sale_fails_closed(self):
        result = telegram_integration.classify_telegram_evidence(
            "Example", self.envelope("claimable", fragment="for_sale")
        )
        self.assertEqual(result["status"], "unknown")
        self.assertNotEqual(result["claimability"], "confirmed")

    def test_direct_purchase_available_is_not_free_claimable(self):
        result = telegram_integration.classify_telegram_evidence(
            "Example", self.envelope("purchasable", fragment="for_sale")
        )
        self.assertEqual(result["status"], "purchasable")
        self.assertEqual(result["claimability"], "purchase_available")
        self.assertNotEqual(result["status"], "claimable")

    def test_direct_invalid_is_invalid(self):
        result = telegram_integration.classify_telegram_evidence(
            "Example", self.envelope("invalid", mtproto="unknown", fragment="unknown")
        )
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["claimability"], "not_claimable")

    def test_legacy_two_absence_signals_still_never_become_green(self):
        result = telegram_integration.classify_telegram_evidence(
            "Example", self.envelope(None)
        )
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["claimability"], "unconfirmed")


class ClaimabilityDiagnosticsTests(unittest.TestCase):
    @patch.dict("verification.diagnostics.os.environ", {}, clear=True)
    def test_unconfigured_strict_providers_are_reported_without_secrets(self):
        result = provider_diagnostics()
        self.assertFalse(result["domain"]["registrar"]["can_confirm_claimability"])
        self.assertFalse(result["telegram"]["authoritative_claimability"])

    @patch.dict(
        "verification.diagnostics.os.environ",
        {
            "NAMECOM_USERNAME": "name-user",
            "NAMECOM_API_TOKEN": "name-secret",
            "TELEGRAM_EVIDENCE_URL": "https://telegram-evidence.internal",
            "TELEGRAM_EVIDENCE_TOKEN": "telegram-secret",
        },
        clear=True,
    )
    def test_configured_strict_providers_are_capability_only(self):
        result = provider_diagnostics()
        self.assertTrue(result["domain"]["registrar"]["can_confirm_claimability"])
        self.assertTrue(result["telegram"]["authoritative_claimability"])
        text = str(result)
        self.assertNotIn("name-secret", text)
        self.assertNotIn("telegram-secret", text)


class StrictClaimabilityUiTests(unittest.TestCase):
    def test_ui_reserves_green_for_claimable(self):
        source = Path("static/claimability_ui.js").read_text(encoding="utf-8")
        self.assertIn("status === 'claimable'", source)
        self.assertIn("status === 'purchasable'", source)
        self.assertIn("cls: 'purchase'", source)
        self.assertIn("=== 'claimable'", source)


if __name__ == "__main__":
    unittest.main()
