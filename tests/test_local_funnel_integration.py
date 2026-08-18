import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import ai_engine
from candidate_funnel import lexical_seeds


class FakeResponses:
    def create(self, **_kwargs):
        return SimpleNamespace(output_text=json.dumps({
            "names": [
                {
                    "name": "Navero",
                    "family": "abstract",
                    "reason": "model",
                    "pronunciation": "na-ve-ro",
                    "language_risks": [],
                }
            ]
        }))


class FakeOpenAI:
    def __init__(self):
        self.responses = FakeResponses()


class LocalFunnelIntegrationTests(unittest.TestCase):
    def test_cyrillic_project_words_become_latin_lexical_seeds(self):
        seeds = lexical_seeds(
            "свіжий лимон сонце енергія",
            {"keywords": ["цитрус", "смак"]},
        )
        self.assertIn("lymon", seeds)
        self.assertIn("sontse", seeds)
        self.assertIn("enerhiya", seeds)
        self.assertIn("tsytrus", seeds)

    def test_new_brand_shortlist_receives_model_and_local_pool(self):
        local = [{
            "name": "Limezest",
            "family": "semantic_compound",
            "reason": "local",
            "pronunciation": "Limezest",
            "language_risks": [],
            "candidate_source": "local_lexical_expansion",
        }]
        fake_module = SimpleNamespace(OpenAI=FakeOpenAI)
        with (
            patch.dict(sys.modules, {"openai": fake_module}),
            patch.dict("os.environ", {"OPENAI_API_KEY": "test"}),
            patch("ai_engine.expand_local_families", return_value=local) as expand,
            patch("ai_engine.select_diverse_names", return_value=[local[0]]) as select,
        ):
            result = ai_engine.generate_ai_names(
                "fresh lime zest",
                1,
                brand_dna={"keywords": ["lime", "zest"]},
            )
        expand.assert_called_once_with(
            "fresh lime zest", {"keywords": ["lime", "zest"]}, limit=180
        )
        candidate_pool = select.call_args.args[0]
        self.assertEqual(candidate_pool[0]["name"], "Navero")
        self.assertEqual(candidate_pool[1]["name"], "Limezest")
        self.assertEqual(result[0]["candidate_source"], "local_lexical_expansion")

    def test_locked_existing_brand_does_not_invent_local_replacement_pool(self):
        fake_module = SimpleNamespace(OpenAI=FakeOpenAI)
        context = {
            "mode": "existing_brand_fixed",
            "brand_name": "Lemon",
            "guidance": "",
        }
        with (
            patch.dict(sys.modules, {"openai": fake_module}),
            patch.dict("os.environ", {"OPENAI_API_KEY": "test"}),
            patch("ai_engine.expand_local_families") as expand,
            patch("ai_engine.select_diverse_names", return_value=[{
                "name": "Navero",
                "family": "abstract",
            }]),
        ):
            ai_engine.generate_ai_names("", 1, search_context=context)
        expand.assert_not_called()


if __name__ == "__main__":
    unittest.main()
