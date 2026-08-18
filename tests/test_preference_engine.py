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

    def automotive_feedback(self):
        feedback = {
            "carcars": {"vote": 1, "comment": ""},
            "cardrive": {"vote": 0, "comment": "Занадто популярне"},
            "drior": {"vote": 1, "comment": ""},
            "karvuno": {"vote": -1, "comment": ""},
            "loler": {"vote": -1, "comment": ""},
            "drute": {"vote": 0, "comment": "Ахаах смішно. Це пздц не прикольно"},
            "kardena": {"vote": 0, "comment": "Дибільне"},
            "metromotor": {"vote": 0, "comment": "Це теж прикольне"},
            "motorcar": {"vote": 1, "comment": ""},
            "motormile": {"vote": 1, "comment": ""},
            "openmile": {"vote": 1, "comment": ""},
            "polomoto": {"vote": 1, "comment": ""},
            "milebridge": {"vote": 1, "comment": ""},
            "urbanroam": {"vote": -1, "comment": ""},
            "varomoto": {"vote": 1, "comment": ""},
            "wacar": {"vote": 1, "comment": ""},
            "goldenmile": {"vote": 1, "comment": "Гарно"},
        }
        family = {
            "carcars": "semantic_compound",
            "cardrive": "semantic_compound",
            "drior": "invented_phonetic",
            "karvuno": "invented_phonetic",
            "loler": "abstract",
            "drute": "invented_phonetic",
            "kardena": "invented_phonetic",
            "metromotor": "semantic_compound",
            "motorcar": "semantic_compound",
            "motormile": "semantic_compound",
            "openmile": "semantic_compound",
            "polomoto": "root_blend",
            "milebridge": "semantic_compound",
            "urbanroam": "semantic_compound",
            "varomoto": "root_blend",
            "wacar": "root_blend",
            "goldenmile": "evocative_metaphor",
        }
        rows = [{"name": name, "family": family[name]} for name in feedback]
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

    def test_real_automotive_feedback_learns_repeated_positive_fragments(self):
        feedback, rows = self.automotive_feedback()
        model = build_taste_model(feedback, rows)
        self.assertIn("mile", model["preferred_fragments"])
        self.assertIn("moto", model["preferred_fragments"])
        self.assertGreater(model["preferred_fragments"]["mile"], 0)
        self.assertGreater(model["preferred_fragments"]["moto"], 0)

        aligned = candidate_preference_score(
            {"name": "SilverMile", "family": "semantic_compound"}, model
        )
        off_pattern = candidate_preference_score(
            {"name": "Karduno", "family": "invented_phonetic"}, model
        )
        self.assertGreater(aligned, off_pattern)

    def test_zero_vote_comments_compile_explicit_directives(self):
        feedback, rows = self.automotive_feedback()
        model = build_taste_model(feedback, rows)
        self.assertIn("cardrive", model["soft_negative_examples"])
        self.assertIn("drute", model["soft_negative_examples"])
        self.assertIn("kardena", model["soft_negative_examples"])
        self.assertIn("metromotor", model["soft_positive_examples"])
        self.assertIn("avoid_generic_or_overpopular", model["comment_directives"])
        self.assertIn("avoid_awkward_or_silly_sound", model["comment_directives"])
        self.assertIn("prefer_elegant_or_clean_sound", model["comment_directives"])

    def test_one_accidental_like_does_not_create_a_fragment_rule(self):
        model = build_taste_model(
            {"zorbex": {"vote": 1, "comment": ""}},
            [{"name": "Zorbex", "family": "invented_phonetic"}],
        )
        self.assertEqual(model["preferred_fragments"], {})
        self.assertEqual(model["avoided_fragments"], {})


if __name__ == "__main__":
    unittest.main()
