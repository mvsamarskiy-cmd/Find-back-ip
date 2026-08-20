from types import SimpleNamespace
import unittest

from creative_generation import install_creative_generation
from creative_lexicon import (
    creative_lexicon_diagnostics,
    creative_palette,
    creative_palette_prompt,
)
from telegram_bootstrap import app


class CreativeLexiconTests(unittest.TestCase):
    def test_automotive_prompt_crosses_into_useful_adjacent_semantics(self):
        palette = creative_palette("car drive repair wheel", guidance="точний автосервіс")
        self.assertIn("mobility", palette["matched_clusters"])
        self.assertTrue(set(palette["bridge_clusters"]) & {"speed", "precision", "freedom", "exploration"})
        self.assertTrue(palette["local_roots"])
        self.assertTrue(set(palette["metaphor_words"]) & {"arrow", "falcon", "wind", "horizon", "compass", "lens"})

    def test_follow_up_batch_rotates_bridge_neighborhood_deterministically(self):
        first = creative_palette("car drive wheel", batch_number=1)
        second = creative_palette("car drive wheel", batch_number=2)
        repeated = creative_palette("car drive wheel", batch_number=2)
        self.assertEqual(second, repeated)
        self.assertEqual(first["matched_clusters"], second["matched_clusters"])
        self.assertNotEqual(first["bridge_clusters"], second["bridge_clusters"])

    def test_palette_respects_explicit_forbidden_roots(self):
        palette = creative_palette("water fresh river", forbidden={"river", "aqua", "spring"})
        combined = set(
            palette["direct_words"]
            + palette["metaphor_words"]
            + palette["classical_roots"]
            + palette["local_roots"]
        )
        self.assertFalse({"river", "aqua", "spring"} & combined)

    def test_palette_is_bounded_and_does_not_dump_dictionary(self):
        palette = creative_palette("nature growth water light craft precision future")
        prompt = creative_palette_prompt(palette)
        self.assertLess(len(prompt), 2400)
        self.assertLessEqual(len(palette["direct_words"]), 16)
        self.assertLessEqual(len(palette["metaphor_words"]), 16)
        self.assertLessEqual(len(palette["local_roots"]), 18)
        diagnostics = creative_lexicon_diagnostics()
        self.assertEqual(diagnostics["network_calls"], 0)
        self.assertFalse(diagnostics["full_dictionary_sent_to_model"])


class CreativeGenerationOverlayTests(unittest.TestCase):
    def fake_module(self, seen):
        module = SimpleNamespace()
        module.BANNED_ROOTS = {"generic"}
        module.BANNED_SUFFIXES = {"ify"}
        module.clean_search_context = lambda value: {
            "mode": (value or {}).get("mode", "new_brand"),
            "brand_name": "",
            "guidance": (value or {}).get("guidance", ""),
        }
        module.clean_generation_context = lambda value: {
            "batch_number": int((value or {}).get("batch_number", 1)),
            "exclude_names": [],
            "conflict_names": [],
            "successful_names": [],
        }
        module.brand_dna_context = lambda value: "BASE_DNA"

        def expand(brief="", brand_dna=None, limit=180):
            seen["expanded_dna"] = brand_dna
            return [{
                "name": "Motriver",
                "family": "root_blend",
                "reason": "fixture",
                "pronunciation": "Motriver",
                "language_risks": [],
            }]
        module.expand_local_families = expand

        def generate(brief, count=10, preferences=None, brand_dna=None, search_context=None, generation_context=None):
            # The creative palette is intentionally request-local and must not be
            # injected into Brand DNA. Observe its two consumers instead: model
            # context and local expansion.
            seen["base_brand_dna"] = brand_dna
            seen["model_context"] = module.brand_dna_context(brand_dna)
            seen["local_rows"] = module.expand_local_families(brief, brand_dna, limit=10)
            return [{
                "name": "Roadora",
                "family": "evocative_metaphor",
                "reason": "fixture",
                "pronunciation": "Roadora",
                "language_risks": [],
            }]
        module.generate_ai_names = generate
        return module

    def test_one_local_retrieval_feeds_both_model_context_and_local_expander(self):
        seen = {}
        module = self.fake_module(seen)
        app_module = SimpleNamespace(generate_ai_names=module.generate_ai_names)
        install_creative_generation(module, app_module)
        rows = app_module.generate_ai_names(
            "car drive repair",
            count=1,
            search_context={"mode": "new_brand", "guidance": "точний автосервіс"},
            generation_context={"batch_number": 1},
        )
        self.assertIn("Internal creative semantic palette", seen["model_context"])
        self.assertIn("mobility", seen["model_context"])
        self.assertIsNone(seen["base_brand_dna"])
        self.assertIn("mobility", seen["expanded_dna"]["themes"])
        self.assertTrue(seen["local_rows"][0]["creative_lexicon_used"])
        self.assertTrue(rows[0]["creative_lexicon_used"])

    def test_compiled_user_word_exclusion_overrides_palette(self):
        seen = {}
        module = self.fake_module(seen)
        install_creative_generation(module)
        module.generate_ai_names(
            "car drive wheel",
            count=1,
            search_context={
                "mode": "new_brand",
                "guidance": "Не використовувати слова: road | коротка назва",
            },
        )
        self.assertNotIn("road", seen["model_context"].lower())
        expanded_keywords = [str(value).lower() for value in seen["expanded_dna"].get("keywords", [])]
        self.assertNotIn("road", expanded_keywords)


class CreativeLexiconDiagnosticsTests(unittest.TestCase):
    def test_production_diagnostics_expose_fast_local_creativity_layer(self):
        diagnostics = app.test_client().get("/api/verification/diagnostics").get_json()
        generation = diagnostics["generation_intelligence"]
        self.assertEqual(generation["creative_lexicon"]["version"], "creative-lexicon-v1")
        self.assertEqual(generation["creative_lexicon"]["network_calls"], 0)
        self.assertEqual(generation["creative_generation"]["extra_model_calls_per_batch"], 0)
        self.assertTrue(generation["creative_generation"]["local_expander_uses_same_palette"])


if __name__ == "__main__":
    unittest.main()
