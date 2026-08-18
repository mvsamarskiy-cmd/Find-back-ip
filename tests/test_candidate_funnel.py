import unittest

from candidate_funnel import rank_candidate_pool, structural_quality
from ai_engine import select_diverse_names


class CandidateFunnelTests(unittest.TestCase):
    def test_balanced_pronounceable_name_scores_above_consonant_cluster(self):
        self.assertGreater(structural_quality("Navero"), structural_quality("Nvrtsk"))

    def test_extreme_length_and_repetition_are_penalized(self):
        self.assertGreater(structural_quality("Lumera"), structural_quality("Luuuumeraaaaa"))
        self.assertGreater(structural_quality("Lumera"), structural_quality("LumeraLumera"))

    def test_rank_candidate_pool_preserves_model_order_on_ties(self):
        rows = [{"name": "Navero", "id": 1}, {"name": "Lumera", "id": 2}]
        ranked = rank_candidate_pool(rows)
        same_scores = ranked[0]["local_quality_score"] == ranked[1]["local_quality_score"]
        if same_scores:
            self.assertEqual([row["id"] for row in ranked], [1, 2])

    def test_rank_candidate_pool_annotates_score(self):
        ranked = rank_candidate_pool([{"name": "Navero"}])
        self.assertIn("local_quality_score", ranked[0])
        self.assertTrue(0 <= ranked[0]["local_quality_score"] <= 100)

    def test_diverse_selector_uses_local_quality_before_external_checks(self):
        rows = [
            {"name": "Nvrtsk", "family": "abstract"},
            {"name": "Navero", "family": "abstract"},
        ]
        selected = select_diverse_names(rows, 1)
        self.assertEqual(selected[0]["name"], "Navero")
        self.assertIn("local_quality_score", selected[0])


if __name__ == "__main__":
    unittest.main()
