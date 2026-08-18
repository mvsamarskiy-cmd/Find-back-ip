import unittest

from preference_engine import (
    build_taste_model,
    candidate_preference_score,
    family_allocation,
)


class PreferenceEngineTests(unittest.TestCase):
    def goose_feedback(self):
        feedback = {
            "wildwing": {"vote": 1, "comment": ""},
            "skyflock": {"vote": 0, "comment": "О це мені подобається, гарно звучить"},
            "wingrove": {"vote": -1, "comment": ""},
            "sovaku": {"vote": -1, "comment": ""},
            "sumi": {"vote": -1, "comment": ""},
            "tavren": {"vote": -1, "comment": ""},
        }
        rows = [
            {"name": "WildWing", "family": "semantic_compound"},
            {"name": "SkyFlock", "family": "semantic_compound"},
            {"name": "Wingrove", "family": "root_blend"},
            {"name": "Sovaku", "family": "invented_phonetic"},
            {"name": "Sumi", "family": "abstract"},
            {"name": "Tavren", "family": "invented_phonetic"},
        ]
        return feedback, rows

    def test_comment_is_soft_positive_without_rewriting_vote(self):
        feedback, rows = self.goose_feedback()
        model = build_taste_model(feedback, rows)
        self.assertIn("skyflock", model["soft_positive_examples"])
        self.assertNotIn("skyflock", model["liked_examples"])

    def test_contrastive_feedback_prefers_meaningful_compound(self):
        feedback, rows = self.goose_feedback()
        model = build_taste_model(feedback, rows)
        good = candidate_preference_score(
            {"name": "DawnFlock", "family": "semantic_compound"}, model
        )
        weak = candidate_preference_score(
            {"name": "Moraku", "family": "invented_phonetic"}, model
        )
        self.assertGreater(good, weak)

    def test_family_allocation_retains_exploration(self):
        feedback, rows = self.goose_feedback()
        model = build_taste_model(feedback, rows)
        allocation = family_allocation(20, model)
        self.assertGreater(
            allocation["semantic_compound"], allocation["invented_phonetic"]
        )
        self.assertTrue(all(value > 0 for value in allocation.values()))
        self.assertAlmostEqual(sum(allocation.values()), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
