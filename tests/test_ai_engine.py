import json
import unittest

from ai_engine import (
    _generation_plan,
    _phonetic_signature,
    _preference_context,
    select_diverse_names,
)


class PreferenceContextTests(unittest.TestCase):
    def test_preference_context_is_bounded_json(self):
        raw = {
            "liked": [f"Like{i}" for i in range(30)],
            "disliked": ["Rovo"],
            "reasons": {"sound": 3, "style": -2},
        }
        result = json.loads(_preference_context(raw))
        self.assertEqual(len(result["liked_examples"]), 20)
        self.assertEqual(result["disliked_examples"], ["Rovo"])
        self.assertEqual(result["reason_weights"], {"sound": 3, "style": -2})

    def test_invalid_feedback_does_not_break_generation_context(self):
        self.assertEqual(_preference_context([]), "No project-specific feedback yet.")

    def test_generation_pool_is_bounded(self):
        self.assertEqual(_generation_plan(5)[0], 13)
        self.assertEqual(_generation_plan(10)[0], 20)
        self.assertEqual(_generation_plan(20)[0], 40)

    def test_phonetic_signature_ignores_vowel_variants(self):
        self.assertEqual(_phonetic_signature("Pryvia"), _phonetic_signature("Pryvio"))

    def test_select_diverse_names_removes_exact_and_near_duplicates(self):
        rows = [
            {"name": "Pryvia"},
            {"name": "pryvia!"},
            {"name": "Pryvio"},
            {"name": "Klykno"},
            {"name": "Zvyazo"},
        ]
        self.assertEqual(
            [row["name"] for row in select_diverse_names(rows, 10)],
            ["Pryvia", "Klykno", "Zvyazo"],
        )

    def test_select_diverse_names_rejects_invalid_rows(self):
        rows = [None, {}, {"name": "12"}, {"name": "Valid"}]
        self.assertEqual(select_diverse_names(rows, 2), [{"name": "Valid"}])


if __name__ == "__main__":
    unittest.main()
