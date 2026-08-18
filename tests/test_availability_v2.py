import unittest
from unittest.mock import patch

import availability_v2


class AvailabilityV2Tests(unittest.TestCase):
    def test_check_all_keeps_legacy_payload_and_adds_verification(self):
        legacy_payload = {
            "availability": {
                "com": {
                    "status": "claimable",
                    "detail": "registrar says yes",
                    "url": "https://example.com",
                    "source": "namecom_core_api",
                    "method": "registrar_check_availability",
                    "confidence": 0.99,
                    "occupancy": "not_found",
                    "claimability": "confirmed",
                    "checked_at": "2026-08-18T00:00:00Z",
                },
                "instagram": {
                    "status": "not_found",
                    "detail": "profile absent",
                    "url": "https://instagram.com/example/",
                    "source": "public_web",
                    "method": "public_profile",
                    "confidence": 0.72,
                    "occupancy": "not_found",
                    "claimability": "unconfirmed",
                    "checked_at": "2026-08-18T00:00:00Z",
                },
            },
            "claimable_count": 1,
            "not_found_count": 1,
            "total_resources": 2,
        }

        with patch.object(availability_v2.legacy, "check_all", return_value=legacy_payload):
            with patch.object(availability_v2, "enrich_instagram", side_effect=lambda name, row: row):
                result = availability_v2.check_all("Example", resources=["com", "instagram"])

        self.assertEqual(result["claimable_count"], 1)
        self.assertEqual(result["not_found_count"], 1)
        self.assertEqual(result["verification"]["com"]["verdict"], "available_verified")
        self.assertEqual(result["verification"]["instagram"]["verdict"], "likely_available")

    def test_instagram_enrichment_recounts_and_updates_verdict(self):
        legacy_payload = {
            "availability": {
                "instagram": {
                    "status": "unknown",
                    "detail": "blocked",
                    "url": "https://instagram.com/natgeo/",
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
            "detail": "occupied",
            "url": "https://instagram.com/natgeo/",
            "source": "socialscan",
            "method": "registration_probe",
            "confidence": 0.9,
            "occupancy": "occupied",
            "claimability": "not_claimable",
            "checked_at": "2026-08-18T00:00:00Z",
        }
        with patch.object(availability_v2.legacy, "check_all", return_value=legacy_payload):
            with patch.object(availability_v2, "enrich_instagram", return_value=enriched):
                result = availability_v2.check_all("natgeo", resources=["instagram"])
        self.assertEqual(result["taken_count"], 1)
        self.assertEqual(result["unknown_count"], 0)
        self.assertEqual(result["verification"]["instagram"]["verdict"], "taken")

    def test_taken_remains_taken(self):
        legacy_payload = {
            "availability": {
                "telegram": {
                    "status": "taken",
                    "source": "public_web",
                    "method": "public_profile",
                    "confidence": 0.85,
                    "checked_at": "2026-08-18T00:00:00Z",
                }
            }
        }
        with patch.object(availability_v2.legacy, "check_all", return_value=legacy_payload):
            result = availability_v2.check_all("Example", resources=["telegram"])
        self.assertEqual(result["verification"]["telegram"]["verdict"], "taken")

    def test_check_many_uses_augmented_checker(self):
        def fake_legacy(name, resources=None):
            return {
                "availability": {
                    "youtube": {
                        "status": "not_found",
                        "source": "youtube_data_api",
                        "method": "official_handle_lookup",
                        "confidence": 0.92,
                        "checked_at": "2026-08-18T00:00:00Z",
                    }
                }
            }

        with patch.object(availability_v2.legacy, "check_all", side_effect=fake_legacy):
            rows = availability_v2.check_many(["alpha", "beta"], max_workers=2, resources=["youtube"])

        self.assertEqual(len(rows), 2)
        self.assertTrue(all("verification" in row for row in rows))
        self.assertTrue(all(row["verification"]["youtube"]["verdict"] == "likely_available" for row in rows))


if __name__ == "__main__":
    unittest.main()
