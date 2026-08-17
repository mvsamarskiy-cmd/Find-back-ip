import json
import unittest

from ai_engine import _preference_context


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


if __name__ == "__main__":
    unittest.main()
