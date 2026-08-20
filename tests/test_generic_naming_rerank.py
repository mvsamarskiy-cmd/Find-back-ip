import unittest

from generic_naming_api import _select_generic_rows, _taste_model_from_preferences


class GenericNamingRerankTests(unittest.TestCase):
    def goose_preferences(self):
        return {
            "liked": ["wildwing"],
            "disliked": ["wingrove", "sovaku", "sumi", "tavren"],
            "feedback": [
                {"name": "wildwing", "vote": 1, "comment": "", "family": "semantic_compound"},
                {"name": "skyflock", "vote": 0, "comment": "О це мені подобається, гарно звучить", "family": "semantic_compound"},
                {"name": "wingrove", "vote": -1, "comment": "", "family": "root_blend"},
                {"name": "sovaku", "vote": -1, "comment": "", "family": "invented_phonetic"},
                {"name": "sumi", "vote": -1, "comment": "", "family": "abstract"},
                {"name": "tavren", "vote": -1, "comment": "", "family": "invented_phonetic"},
            ],
        }

    def test_goose_feedback_moves_generic_reranker_toward_meaningful_names(self):
        model = _taste_model_from_preferences(self.goose_preferences())
        rows = [
            {"name": "DawnFlock", "family": "semantic_compound"},
            {"name": "RiverWing", "family": "evocative_metaphor"},
            {"name": "PlumePath", "family": "evocative_metaphor"},
            {"name": "Moraku", "family": "invented_phonetic"},
            {"name": "Pevanu", "family": "invented_phonetic"},
            {"name": "Toremi", "family": "invented_phonetic"},
        ]

        selected = _select_generic_rows(rows, 6, model)
        by_name = {row["name"]: row for row in selected}

        self.assertGreater(by_name["DawnFlock"]["user_fit_score"], by_name["Moraku"]["user_fit_score"])
        self.assertLess(
            next(i for i, row in enumerate(selected) if row["name"] == "DawnFlock"),
            next(i for i, row in enumerate(selected) if row["name"] == "Moraku"),
        )

    def test_generic_reranker_keeps_diversity_and_requested_count(self):
        model = _taste_model_from_preferences(self.goose_preferences())
        rows = [
            {"name": "SkyTrail", "family": "semantic_compound"},
            {"name": "DawnFlock", "family": "semantic_compound"},
            {"name": "WildGlide", "family": "semantic_compound"},
            {"name": "CloudRoam", "family": "semantic_compound"},
            {"name": "PlumePath", "family": "evocative_metaphor"},
            {"name": "AerieWay", "family": "evocative_metaphor"},
            {"name": "FeatherRun", "family": "root_blend"},
            {"name": "Moraku", "family": "invented_phonetic"},
        ]

        selected = _select_generic_rows(rows, 6, model)
        families = {row["family"] for row in selected}

        self.assertEqual(len(selected), 6)
        self.assertGreaterEqual(len(families), 3)
        self.assertTrue(all("user_fit_score" in row for row in selected))
        self.assertTrue(all("adaptive_relevance_score" in row for row in selected))


if __name__ == "__main__":
    unittest.main()
