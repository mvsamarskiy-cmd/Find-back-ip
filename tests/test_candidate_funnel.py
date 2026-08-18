import unittest

from candidate_funnel import (
    LOCAL_SOURCE,
    expand_local_families,
    lexical_seeds,
    rank_candidate_pool,
    structural_quality,
)
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

    def test_lexical_seeds_use_brief_and_structured_dna(self):
        seeds = lexical_seeds(
            "Fresh citrus drinks for Warsaw",
            {
                "themes": ["sun energy"],
                "keywords": ["lime", "zest"],
                "summary": "bright refreshment",
            },
        )
        self.assertIn("citrus", seeds)
        self.assertIn("lime", seeds)
        self.assertIn("zest", seeds)
        self.assertIn("energy", seeds)
        self.assertNotIn("brand", seeds)

    def test_local_family_expansion_is_bounded_and_deterministic(self):
        dna = {"keywords": ["lime", "zest", "sun", "fresh"]}
        first = expand_local_families("citrus energy", dna, limit=25)
        second = expand_local_families("citrus energy", dna, limit=25)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 25)
        self.assertGreater(len(first), 10)
        self.assertTrue(all(row["candidate_source"] == LOCAL_SOURCE for row in first))
        self.assertTrue(all(row["family"] in {"semantic_compound", "root_blend", "invented_phonetic"} for row in first))

    def test_local_expansion_uses_composition_not_one_letter_typo_mutations(self):
        rows = expand_local_families(
            "lime citrus",
            {"keywords": ["zest", "fresh"]},
            limit=40,
        )
        names = {row["name"].lower() for row in rows}
        self.assertFalse(any(name in {"limee", "limes", "limex"} for name in names))
        self.assertTrue(any("lime" in name and name != "lime" for name in names))

    def test_local_rows_receive_small_prior_penalty(self):
        model = rank_candidate_pool([{"name": "Navero"}])[0]
        local = rank_candidate_pool([{
            "name": "Navero",
            "candidate_source": LOCAL_SOURCE,
        }])[0]
        self.assertEqual(model["local_quality_score"] - local["local_quality_score"], 6)


if __name__ == "__main__":
    unittest.main()
