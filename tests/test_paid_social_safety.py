import unittest

from verification.bridge import legacy_result_to_evidence
from verification.fusion import fuse_evidence


class PaidSocialSafetyTests(unittest.TestCase):
    def test_paid_telegram_marketplace_is_reserved_not_verified_free(self):
        evidence = legacy_result_to_evidence(
            "telegram",
            "premiumname",
            {
                "status": "purchasable",
                "source": "telegram_evidence_service",
                "method": "mtproto_fragment",
                "confidence": 0.95,
                "offer": {"provider": "fragment", "purchase_price": 420, "currency": "TON"},
            },
        )
        self.assertEqual(evidence.signal, "reserved")
        self.assertEqual(evidence.metadata["raw_status"], "purchasable")
        verdict = fuse_evidence("telegram", "premiumname", [evidence.to_dict()])
        self.assertEqual(verdict.verdict, "reserved")
        self.assertNotEqual(verdict.verdict, "available_verified")

    def test_purchasable_domain_remains_actionable(self):
        evidence = legacy_result_to_evidence(
            "com",
            "premium.example.com",
            {
                "status": "purchasable",
                "source": "namecom_core_api",
                "method": "registrar_check_availability",
                "confidence": 0.99,
                "offer": {"provider": "name.com", "premium": True},
            },
        )
        self.assertEqual(evidence.signal, "purchasable")
        verdict = fuse_evidence("com", "premium.example.com", [evidence.to_dict()])
        self.assertEqual(verdict.verdict, "available_verified")


if __name__ == "__main__":
    unittest.main()
