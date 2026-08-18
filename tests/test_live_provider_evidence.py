import unittest
from unittest.mock import patch

from verification.fusion import fuse_evidence
from verification.live_provider_evidence import (
    apply_compatibility_evidence,
    collect_live_provider_evidence,
)


LEGACY_UNKNOWN = {
    "status": "unknown",
    "detail": "inconclusive",
    "url": "https://example.test/user",
    "source": "public_web",
    "method": "public_profile",
    "confidence": 0.0,
    "occupancy": "unknown",
    "claimability": "unconfirmed",
}


class LiveProviderEvidenceTests(unittest.TestCase):
    @patch.dict("verification.live_provider_evidence.os.environ", {}, clear=True)
    def test_socialscan_claimable_is_downgraded_to_absence_only(self):
        with patch(
            "verification.live_provider_evidence.socialscan_adapter.check_username",
            return_value={
                "platform": "x",
                "handle": "example",
                "source": "socialscan",
                "method": "registration_probe",
                "signal": "claimable",
                "confidence": 0.86,
                "metadata": {},
            },
        ):
            rows = collect_live_provider_evidence("example", {"x": dict(LEGACY_UNKNOWN)})

        evidence = rows["x"][0]
        self.assertEqual(evidence["signal"], "absent")
        self.assertLessEqual(evidence["confidence"], 0.78)
        self.assertEqual(evidence["metadata"]["raw_signal"], "claimable")

    def test_telegram_collects_fragment_and_whatsmyname_independently(self):
        with patch(
            "verification.live_provider_evidence.fragment_username_adapter.check_username",
            return_value={
                "platform": "telegram",
                "handle": "durov",
                "source": "fragment_public_web",
                "method": "fragment_username_status",
                "signal": "exists",
                "confidence": 0.95,
                "metadata": {},
            },
        ) as fragment:
            with patch(
                "verification.live_provider_evidence.whatsmyname_adapter.check_username",
                return_value={
                    "platform": "telegram",
                    "handle": "durov",
                    "source": "whatsmyname",
                    "method": "community_fingerprint",
                    "signal": "absent",
                    "confidence": 0.68,
                    "metadata": {},
                },
            ) as wmn:
                rows = collect_live_provider_evidence("durov", {"telegram": dict(LEGACY_UNKNOWN)})

        fragment.assert_called_once_with("durov", "telegram")
        wmn.assert_called_once_with("durov", "telegram")
        self.assertEqual(len(rows["telegram"]), 2)
        by_source = {row["source"]: row for row in rows["telegram"]}
        self.assertEqual(by_source["fragment_public_web"]["signal"], "exists")
        self.assertTrue(by_source["whatsmyname"]["metadata"]["non_blocking"])

        compatibility = apply_compatibility_evidence(
            "durov", "telegram", dict(LEGACY_UNKNOWN), rows["telegram"]
        )
        self.assertEqual(compatibility["status"], "taken")
        self.assertEqual(compatibility["source"], "fragment_public_web")

    def test_fragment_marketplace_path_is_normalized_to_reserved(self):
        with patch(
            "verification.live_provider_evidence.fragment_username_adapter.check_username",
            return_value={
                "platform": "telegram",
                "handle": "premiumname",
                "source": "fragment_public_web",
                "method": "fragment_username_status",
                "signal": "purchasable",
                "confidence": 0.9,
                "metadata": {},
            },
        ):
            with patch(
                "verification.live_provider_evidence.whatsmyname_adapter.check_username",
                return_value={
                    "platform": "telegram",
                    "handle": "premiumname",
                    "source": "whatsmyname",
                    "method": "community_fingerprint",
                    "signal": "unknown",
                    "confidence": 0.0,
                    "metadata": {},
                },
            ):
                rows = collect_live_provider_evidence(
                    "premiumname", {"telegram": dict(LEGACY_UNKNOWN)}
                )

        fragment = next(row for row in rows["telegram"] if row["source"] == "fragment_public_web")
        self.assertEqual(fragment["signal"], "reserved")
        self.assertEqual(fragment["metadata"]["raw_signal"], "purchasable")
        compatibility = apply_compatibility_evidence(
            "premiumname", "telegram", dict(LEGACY_UNKNOWN), rows["telegram"]
        )
        self.assertEqual(compatibility["status"], "reserved")
        self.assertNotIn(compatibility["status"], {"claimable", "purchasable"})

    def test_terminal_legacy_telegram_skips_secondary_providers(self):
        taken = dict(LEGACY_UNKNOWN)
        taken["status"] = "taken"
        with patch(
            "verification.live_provider_evidence.fragment_username_adapter.check_username"
        ) as fragment:
            with patch(
                "verification.live_provider_evidence.whatsmyname_adapter.check_username"
            ) as wmn:
                rows = collect_live_provider_evidence("telegram", {"telegram": taken})
        self.assertEqual(rows, {})
        fragment.assert_not_called()
        wmn.assert_not_called()

    def test_non_blocking_false_negative_is_visible_but_cannot_drive_verdict(self):
        verdict = fuse_evidence(
            "telegram",
            "mazomoto",
            [
                {
                    "platform": "telegram",
                    "handle": "mazomoto",
                    "source": "whatsmyname",
                    "method": "community_fingerprint",
                    "signal": "absent",
                    "confidence": 0.68,
                    "metadata": {"non_blocking": True},
                }
            ],
        )
        self.assertEqual(verdict.verdict, "unknown")
        self.assertEqual(len(verdict.evidence), 1)
        self.assertEqual(verdict.evidence[0]["signal"], "absent")


if __name__ == "__main__":
    unittest.main()
