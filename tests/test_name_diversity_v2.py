import unittest

from ai_engine import (
    GENERATION_FAMILY_KEYS,
    SCHEMA,
    _edit_distance,
    _too_similar,
    _visual_signature,
    select_diverse_names,
)


class NameDiversityV2Tests(unittest.TestCase):
    def test_schema_requires_explicit_family(self):
        item = SCHEMA["properties"]["names"]["items"]
        self.assertIn("family", item["required"])
        self.assertEqual(
            set(item["properties"]["family"]["enum"]),
            set(GENERATION_FAMILY_KEYS),
        )

    def test_single_edit_variants_are_rejected(self):
        self.assertEqual(_edit_distance("Zeston", "Zestonx", 1), 1)
        self.assertTrue(_too_similar("Zeston", "Zestonx"))

    def test_visual_rn_m_confusion_is_rejected(self):
        self.assertEqual(_visual_signature("Marnet"), _visual_signature("Mamet"))
        self.assertTrue(_too_similar("Marnet", "Mamet"))

    def test_family_quota_prevents_monoculture(self):
        rows = [
            {
                "name": name,
                "family": "root_blend",
                "reason": "x",
                "pronunciation": "x",
                "language_risks": [],
            }
            for name in ("Zaneko", "Buremi", "Caluto", "Doveki", "Fenaru")
        ]
        rows += [
            {
                "name": "Northen",
                "family": "evocative_metaphor",
                "reason": "x",
                "pronunciation": "x",
                "language_risks": [],
            },
            {
                "name": "Quvexa",
                "family": "invented_phonetic",
                "reason": "x",
                "pronunciation": "x",
                "language_risks": [],
            },
        ]
        selected = select_diverse_names(rows, 5)
        families = [row["family"] for row in selected]
        self.assertLessEqual(families.count("root_blend"), 2)
        self.assertIn("evocative_metaphor", families)
        self.assertIn("invented_phonetic", families)

    def test_legacy_rows_without_family_still_pass_selector(self):
        selected = select_diverse_names([{"name": "Nuvexa"}], 1)
        self.assertEqual([row["name"] for row in selected], ["Nuvexa"])
        self.assertIn("local_quality_score", selected[0])


if __name__ == "__main__":
    unittest.main()
