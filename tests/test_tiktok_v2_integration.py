from unittest import TestCase
from unittest.mock import patch

import availability_v2


class TikTokV2IntegrationTests(TestCase):
    def test_tiktok_enrichment_updates_counts_and_verdict(self):
        legacy_payload = {
            "availability": {
                "tiktok": {
                    "status": "unknown",
                    "detail": "inconclusive",
                    "url": "https://www.tiktok.com/@mazomoto",
                    "source": "public_web",
                    "method": "public_profile",
                    "confidence": 0.0,
                    "occupancy": "unknown",
                    "claimability": "unconfirmed",
                    "checked_at": "2026-08-18T00:00:00Z",
                }
            }
        }
        enriched = {
            "status": "taken",
            "detail": "exact TikTok profile",
            "url": "https://www.tiktok.com/@mazomoto",
            "source": "tiktok_oembed",
            "method": "official_creator_profile_oembed",
            "confidence": 0.97,
            "occupancy": "occupied",
            "claimability": "not_claimable",
            "checked_at": "2026-08-18T00:00:00Z",
        }
        with patch.object(availability_v2.legacy, "check_all", return_value=legacy_payload):
            with patch.object(availability_v2, "enrich_tiktok", return_value=enriched):
                result = availability_v2.check_all("mazomoto", resources=["tiktok"])

        self.assertEqual(result["taken_count"], 1)
        self.assertEqual(result["unknown_count"], 0)
        self.assertEqual(result["verification"]["tiktok"]["verdict"], "taken")
