import unittest

from trademark_risk import (
    assess_supplied_matches,
    clean_trademark_context,
    trademark_search_plan,
)


class TrademarkRiskTests(unittest.TestCase):
    def test_default_scope_is_eu_poland_and_international(self):
        self.assertEqual(
            clean_trademark_context(None),
            {"territories": ["EU", "PL", "INTL"], "nice_classes": []},
        )

    def test_context_validates_classes_and_territories(self):
        self.assertEqual(
            clean_trademark_context({
                "territories": ["pl", "EU", "pl"],
                "nice_classes": [42, "35", 42],
            }),
            {"territories": ["PL", "EU"], "nice_classes": [35, 42]},
        )
        with self.assertRaises(ValueError):
            clean_trademark_context({"territories": ["US"], "nice_classes": []})
        with self.assertRaises(ValueError):
            clean_trademark_context({"territories": ["EU"], "nice_classes": [46]})

    def test_search_plan_never_calls_no_hit_free(self):
        plan = trademark_search_plan("Limeon", {"territories": ["EU"], "nice_classes": [35]})
        self.assertEqual(plan["risk"], "unknown")
        self.assertEqual(plan["assessment"], "manual_search_required")
        self.assertIn("No-hit is not proof", plan["notice"])
        self.assertEqual(plan["nice_classes"], [35])
        self.assertIn("euipo_tmview", plan["sources"])
        self.assertEqual(
            plan["sources"]["wipo"]["automation"],
            "prohibited_on_public_search_service",
        )

    def test_exact_active_relevant_match_is_high_risk(self):
        result = assess_supplied_matches(
            "Limeon",
            [{
                "mark": "LIMEON",
                "status": "registered",
                "territory": "EU",
                "nice_classes": [35],
                "similarity": 1.0,
            }],
            {"territories": ["EU"], "nice_classes": [35]},
        )
        self.assertEqual(result["risk"], "high")
        self.assertEqual(result["match_counts"]["exact_active"], 1)
        self.assertEqual(result["match_counts"]["relevant_active"], 1)

    def test_similar_relevant_active_match_is_medium_risk(self):
        result = assess_supplied_matches(
            "Limeon",
            [{
                "mark": "Limeone",
                "status": "pending",
                "territory": "EU",
                "nice_classes": [42],
                "similarity": 0.88,
            }],
            {"territories": ["EU"], "nice_classes": [42]},
        )
        self.assertEqual(result["risk"], "medium")
        self.assertEqual(result["match_counts"]["similar_active"], 1)

    def test_observations_without_relevant_collision_are_low_observed_not_free(self):
        result = assess_supplied_matches(
            "Limeon",
            [{
                "mark": "Other",
                "status": "registered",
                "territory": "EU",
                "nice_classes": [9],
                "similarity": 0.2,
            }],
            {"territories": ["EU"], "nice_classes": [35]},
        )
        self.assertEqual(result["risk"], "low_observed")
        self.assertNotEqual(result["risk"], "free")

    def test_empty_observations_remain_unknown(self):
        result = assess_supplied_matches("Limeon", [], {"territories": ["PL"]})
        self.assertEqual(result["risk"], "unknown")


if __name__ == "__main__":
    unittest.main()
