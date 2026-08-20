import json
import types
import unittest

import session_api as session_api_module
from telegram_bootstrap import app


class RankingPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.app_module = types.SimpleNamespace(
            RESOURCE_KEYS={"com", "instagram", "telegram", "tiktok", "youtube", "facebook", "x"}
        )

    def test_ranking_breakdown_survives_candidate_sanitizer(self):
        raw = {
            "name": "DawnFlock",
            "checked": True,
            "availability": {"com": {"status": "claimable", "confidence": 0.99}},
            "verification": {},
            "structural_quality_score": 84.2,
            "linguistic_quality_score": 88.6,
            "name_quality_score": 86.1,
            "user_fit_score": 91.4,
            "adaptive_relevance_score": 89.7,
            "identity_relevance_score": 88.1,
            "availability_opportunity_score": 100.0,
            "availability_evidence_confidence_score": 99.0,
            "verification_coverage_score": 100.0,
            "final_score": 91.4,
            "availability_state": "claimable",
            "bundle_availability_state": "claimable",
            "ranking_model": "final-v1",
            "ranking_reason": "якість назви 86/100 · відповідність смаку 91/100 · вільність підтверджена",
            "bundle_claimable": ["com"],
            "bundle_purchasable": [],
        }
        clean = session_api_module._clean_candidate(raw, self.app_module)
        for key in (
            "structural_quality_score", "linguistic_quality_score", "name_quality_score",
            "user_fit_score", "adaptive_relevance_score", "identity_relevance_score",
            "availability_opportunity_score", "availability_evidence_confidence_score",
            "verification_coverage_score", "final_score", "availability_state",
            "bundle_availability_state", "ranking_model", "ranking_reason",
            "bundle_claimable", "bundle_purchasable",
        ):
            self.assertIn(key, clean)
        self.assertEqual(clean["ranking_model"], "final-v1")
        self.assertEqual(clean["bundle_claimable"], ["com"])
        self.assertEqual(clean["bundle_purchasable"], [])
        self.assertLess(
            len(json.dumps(clean, ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
            session_api_module.MAX_CANDIDATE_BYTES,
        )

    def test_ranking_numbers_are_bounded_and_non_finite_values_are_dropped(self):
        clean = session_api_module._clean_candidate({
            "name": "SkyFlock",
            "availability": {},
            "verification": {},
            "final_score": 999,
            "user_fit_score": -50,
            "adaptive_relevance_score": "NaN",
            "availability_opportunity_score": float("inf"),
        }, self.app_module)
        self.assertEqual(clean["final_score"], 100.0)
        self.assertEqual(clean["user_fit_score"], 0.0)
        self.assertNotIn("adaptive_relevance_score", clean)
        self.assertNotIn("availability_opportunity_score", clean)

    def test_ranking_reason_is_bounded(self):
        clean = session_api_module._clean_candidate({
            "name": "RiverWing",
            "availability": {},
            "verification": {},
            "ranking_reason": "x" * 5000,
        }, self.app_module)
        self.assertEqual(len(clean["ranking_reason"]), 600)

    def test_diagnostics_advertise_durable_scores(self):
        diagnostics = app.test_client().get("/api/verification/diagnostics").get_json()
        self.assertTrue(diagnostics["final_ranking"]["durable_scores"])
        self.assertEqual(diagnostics["final_ranking"]["model"], "final-v1")


if __name__ == "__main__":
    unittest.main()
