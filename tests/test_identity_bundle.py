import unittest

from identity_bundle import (
    classify_identity_bundle,
    normalize_required_resources,
    score_identity_bundle,
)


class IdentityBundleTests(unittest.TestCase):
    def test_required_defaults_to_every_selected_resource(self):
        self.assertEqual(
            normalize_required_resources(None, ["telegram", "com"]),
            ("com", "telegram"),
        )

    def test_required_must_be_selected(self):
        with self.assertRaises(ValueError):
            normalize_required_resources(["youtube"], ["telegram"])

    def test_taken_required_resource_is_conflict(self):
        result = classify_identity_bundle({
            "com": {"status": "claimable"},
            "telegram": {"status": "taken"},
        }, ["com", "telegram"])
        self.assertEqual(result["bundle_state"], "conflict")
        self.assertEqual(result["bundle_conflicts"], ["telegram"])
        self.assertEqual(result["bundle_score"], 0)
        self.assertEqual(result["bundle_grade"], "blocked")

    def test_all_actionable_required_resources_are_confirmed(self):
        result = classify_identity_bundle({
            "com": {"status": "claimable", "confidence": 1.0},
            "telegram": {"status": "purchasable", "confidence": 1.0},
        }, ["com", "telegram"])
        self.assertEqual(result["bundle_state"], "confirmed")
        self.assertEqual(result["bundle_promising"], [])
        self.assertGreaterEqual(result["bundle_score"], 85)
        self.assertEqual(result["bundle_grade"], "strong")

    def test_not_found_is_promising_not_confirmed(self):
        result = classify_identity_bundle({
            "com": {"status": "claimable", "confidence": 1.0},
            "instagram": {"status": "not_found", "confidence": 1.0},
        }, ["com", "instagram"])
        self.assertEqual(result["bundle_state"], "promising")
        self.assertEqual(result["bundle_promising"], ["instagram"])
        self.assertLess(result["bundle_score"], 100)
        self.assertNotEqual(result["bundle_grade"], "blocked")

    def test_unknown_or_missing_required_resource_is_unresolved(self):
        explicit = classify_identity_bundle({
            "telegram": {"status": "unknown"},
        }, ["telegram"])
        missing = classify_identity_bundle({}, ["telegram"])
        self.assertEqual(explicit["bundle_state"], "unresolved")
        self.assertEqual(missing["bundle_state"], "unresolved")
        self.assertLessEqual(explicit["bundle_score"], 49)
        self.assertEqual(explicit["bundle_grade"], "unresolved")

    def test_conflict_wins_when_another_required_resource_is_unresolved(self):
        result = classify_identity_bundle({
            "com": {"status": "taken"},
            "telegram": {"status": "rate_limited"},
        }, ["com", "telegram"])
        self.assertEqual(result["bundle_state"], "conflict")
        self.assertEqual(result["bundle_conflicts"], ["com"])
        self.assertEqual(result["bundle_score"], 0)

    def test_optional_taken_resource_cannot_block_required_bundle(self):
        result = classify_identity_bundle({
            "com": {"status": "claimable", "confidence": 1.0},
            "telegram": {"status": "claimable", "confidence": 1.0},
            "youtube": {"status": "taken", "confidence": 1.0},
        }, ["com", "telegram"])
        self.assertEqual(result["bundle_state"], "confirmed")
        self.assertEqual(result["optional_resources"], ["youtube"])
        self.assertEqual(result["required_score"], 100)
        self.assertEqual(result["optional_score"], 0)
        self.assertEqual(result["bundle_score"], 80)
        self.assertEqual(result["bundle_grade"], "good")

    def test_optional_claimable_resource_improves_ranking(self):
        weaker = score_identity_bundle({
            "com": {"status": "claimable", "confidence": 1.0},
            "telegram": {"status": "not_found", "confidence": 1.0},
            "youtube": {"status": "taken", "confidence": 1.0},
        }, ["com", "telegram"])
        stronger = score_identity_bundle({
            "com": {"status": "claimable", "confidence": 1.0},
            "telegram": {"status": "not_found", "confidence": 1.0},
            "youtube": {"status": "claimable", "confidence": 1.0},
        }, ["com", "telegram"])
        self.assertGreater(stronger["bundle_score"], weaker["bundle_score"])

    def test_confidence_changes_rank_not_semantic_classification(self):
        low = classify_identity_bundle({
            "com": {"status": "not_found", "confidence": 0.2},
        }, ["com"])
        high = classify_identity_bundle({
            "com": {"status": "not_found", "confidence": 0.95},
        }, ["com"])
        self.assertEqual(low["bundle_state"], "promising")
        self.assertEqual(high["bundle_state"], "promising")
        self.assertGreater(high["bundle_score"], low["bundle_score"])

    def test_legacy_available_is_unresolved_not_confirmed(self):
        result = classify_identity_bundle({
            "telegram": {"status": "available", "confidence": 1.0},
        }, ["telegram"])
        self.assertEqual(result["bundle_state"], "unresolved")
        self.assertLessEqual(result["bundle_score"], 49)


if __name__ == "__main__":
    unittest.main()
