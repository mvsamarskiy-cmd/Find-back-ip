import json
import unittest

from ai_engine import (
    BANNED_ROOTS,
    BANNED_SUFFIXES,
    SYSTEM_PROMPT,
    _generation_plan,
    _is_allowed_name,
    _phonetic_signature,
    _preference_context,
    clean_generation_context,
    clean_search_context,
    generation_context_prompt,
    search_context_prompt,
    select_diverse_names,
)


def alpha_name(prefix, index):
    return prefix + chr(65 + ((index // 26) % 26)) + chr(65 + (index % 26))


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

    def test_search_context_defaults_to_new_brand(self):
        self.assertEqual(
            clean_search_context(None),
            {"mode": "new_brand", "brand_name": "", "guidance": ""},
        )

    def test_existing_brand_search_requires_brand_name(self):
        with self.assertRaises(ValueError):
            clean_search_context({"mode": "existing_brand_fixed"})

    def test_search_context_rejects_unknown_mode_and_long_guidance(self):
        with self.assertRaises(ValueError):
            clean_search_context({"mode": "surprise_me"})
        with self.assertRaises(ValueError):
            clean_search_context({"mode": "new_brand", "guidance": "x" * 501})

    def test_fixed_brand_prompt_locks_brand_and_keeps_guidance(self):
        data = json.loads(search_context_prompt({
            "mode": "existing_brand_fixed",
            "brand_name": "Lemon",
            "guidance": "Не використовуй official",
        }))
        self.assertEqual(data["existing_brand"], "Lemon")
        self.assertEqual(data["additional_guidance"], "Не використовуй official")
        self.assertIn("Do not rename", data["task_rule"])

    def test_generation_context_is_bounded_and_sanitized(self):
        context = clean_generation_context({
            "batch_number": 99,
            "exclude_names": [alpha_name("Name", i) for i in range(120)] + ["bad-name"],
            "conflict_names": [alpha_name("Conflict", i) for i in range(50)],
            "successful_names": [alpha_name("Good", i) for i in range(30)],
        })
        self.assertEqual(context["batch_number"], 5)
        self.assertEqual(len(context["exclude_names"]), 100)
        self.assertEqual(len(context["conflict_names"]), 40)
        self.assertEqual(len(context["successful_names"]), 20)
        self.assertTrue(all(name.isascii() and name.isalpha() for name in context["exclude_names"]))

    def test_generation_context_rejects_non_object(self):
        with self.assertRaises(ValueError):
            clean_generation_context(["not", "an", "object"])

    def test_follow_up_batch_prompt_forces_semantic_broadening(self):
        data = json.loads(generation_context_prompt({
            "batch_number": 2,
            "exclude_names": ["Lemonbox"],
            "conflict_names": ["Lemonbox"],
            "successful_names": ["Northly"],
        }))
        self.assertEqual(data["batch_number"], 2)
        self.assertIn("Lemonbox", data["excluded_names"])
        self.assertIn("different semantic", data["adaptation_rule"])

    def test_existing_brand_variants_do_not_use_new_brand_blacklist(self):
        context = {"mode": "existing_brand_fixed", "brand_name": "Tech", "guidance": ""}
        self.assertTrue(_is_allowed_name("TechClub", context))
        self.assertFalse(_is_allowed_name("TechClub2", context))

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

    def test_select_diverse_names_excludes_prior_batch_near_duplicates(self):
        rows = [
            {"name": "Pryvio"},
            {"name": "Klykno"},
        ]
        self.assertEqual(
            select_diverse_names(rows, 10, exclude_names=["Pryvia"]),
            [{"name": "Klykno"}],
        )

    def test_select_diverse_names_rejects_invalid_rows(self):
        rows = [
            None,
            {},
            {"name": "12"},
            {"name": "Спільнодум"},
            {"name": "Véya"},
            {"name": "IdeaSync"},
            {"name": "VoteNest"},
            {"name": "BrightHub"},
            {"name": "Valid"},
        ]
        self.assertEqual(select_diverse_names(rows, 10), [{"name": "Valid"}])

    def test_allowed_name_enforces_ascii_and_blacklist(self):
        self.assertTrue(_is_allowed_name("Nuvexa"))
        self.assertFalse(_is_allowed_name("Nuvexa2"))
        self.assertFalse(_is_allowed_name("Nuvéxa"))
        self.assertFalse(_is_allowed_name("IdeaNest"))
        self.assertFalse(_is_allowed_name("BrightHub"))

    def test_generation_plan_contains_canonical_blacklist(self):
        plan = _generation_plan(5)[1]
        self.assertIn("Forbidden roots", plan)
        self.assertIn("Forbidden endings", plan)
        self.assertTrue(BANNED_ROOTS.issubset(set(plan.replace(",", "").replace(".", "").split())))
        self.assertTrue(BANNED_SUFFIXES.issubset(set(plan.replace(",", "").replace(".", "").split())))

    def test_follow_up_generation_plan_moves_neighborhood(self):
        plan = _generation_plan(10, generation_context={"batch_number": 2})[1]
        self.assertIn("follow-up batch", plan)
        self.assertIn("change lexical and phonetic neighborhoods", plan)

    def test_prompt_requires_ascii_latin_names(self):
        self.assertIn("ASCII Latin letters A-Z", SYSTEM_PROMPT)
        self.assertIn("existing brand is locked", SYSTEM_PROMPT)
        self.assertIn("prior batches", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
