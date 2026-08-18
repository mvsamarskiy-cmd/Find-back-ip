import json
import unittest
from unittest.mock import MagicMock, patch

import app
from prompt_intelligence import INTENT_SYSTEM_PROMPT, clean_intelligence, interpret_prompt


class PromptIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_short_category_prompt_is_expected_to_expand_not_be_repeated(self):
        self.assertIn("short category prompts", INTENT_SYSTEM_PROMPT)
        self.assertIn("EXPAND", INTENT_SYSTEM_PROMPT)
        self.assertIn("Do not merely transliterate or repeat", INTENT_SYSTEM_PROMPT)
        self.assertIn("naming_roots", INTENT_SYSTEM_PROMPT)

    def test_instruction_glue_is_explicitly_excluded_from_naming_roots(self):
        for token in ("want", "need", "find", "name", "for", "please"):
            self.assertIn(token, INTENT_SYSTEM_PROMPT)
        self.assertIn("must not become naming roots", INTENT_SYSTEM_PROMPT)

    def test_clean_intelligence_keeps_checkbox_resources_as_explicit_selection(self):
        raw = self._intent(
            entity_type="автосервіс",
            naming_roots=["repair", "torque", "motion"],
            inferred_requested_resources=["telegram"],
        )
        cleaned = clean_intelligence(raw, "автосервіс", ["instagram"])
        self.assertEqual(cleaned["selected_resources"], ["instagram"])
        self.assertEqual(cleaned["inferred_requested_resources"], ["telegram"])
        self.assertEqual(cleaned["naming_roots"], ["repair", "torque", "motion"])

    def test_clean_intelligence_extracts_url_from_human_prompt(self):
        raw = self._intent(website_urls=[])
        cleaned = clean_intelligence(
            raw,
            "Маю сайт https://example.com/about, треба Instagram",
            ["instagram"],
        )
        self.assertEqual(cleaned["website_urls"], ["https://example.com/about"])

    def test_new_brand_cannot_keep_accidental_brand_name(self):
        raw = self._intent(search_mode="new_brand", brand_name="Avtoservis", brand_lock="fixed")
        cleaned = clean_intelligence(raw, "автосервіс", ["instagram"])
        self.assertEqual(cleaned["search_mode"], "new_brand")
        self.assertEqual(cleaned["brand_name"], "")
        self.assertEqual(cleaned["brand_lock"], "new")

    @patch.dict("prompt_intelligence.os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("openai.OpenAI")
    def test_interpreter_uses_structured_ai_output_for_one_word_prompt(self, openai_cls):
        response = MagicMock()
        response.output_text = json.dumps(self._intent(
            entity_type="автомобільний сервіс",
            semantic_brief="Створити новий бренд для автосервісу з акцентом на точність, надійність і рух.",
            core_concepts=["ремонт", "точність", "рух"],
            naming_roots=["repair", "torque", "motion", "drive", "craft"],
            confidence="high",
        ), ensure_ascii=False)
        openai_cls.return_value.responses.create.return_value = response

        result = interpret_prompt("автосервіс", ["instagram"])

        self.assertEqual(result["search_mode"], "new_brand")
        self.assertEqual(result["selected_resources"], ["instagram"])
        self.assertIn("torque", result["naming_roots"])
        call = openai_cls.return_value.responses.create.call_args.kwargs
        self.assertIn("автосервіс", call["input"])
        self.assertIn("instagram", call["input"])
        self.assertEqual(call["text"]["format"]["type"], "json_schema")

    @patch("app.interpret_prompt")
    def test_interpret_endpoint_passes_selected_resources(self, interpret):
        interpret.return_value = self._cleaned_response()
        response = self.client.post(
            "/api/interpret",
            json={"prompt": "колеса до машин", "resources": ["instagram"]},
            environ_base={"REMOTE_ADDR": "198.51.100.91"},
        )
        self.assertEqual(response.status_code, 200)
        interpret.assert_called_once_with("колеса до машин", ("instagram",), None)

    @patch("app.interpret_prompt")
    def test_interpret_endpoint_rejects_empty_resource_selection_before_ai(self, interpret):
        response = self.client.post(
            "/api/interpret",
            json={"prompt": "автосервіс", "resources": []},
            environ_base={"REMOTE_ADDR": "198.51.100.92"},
        )
        self.assertEqual(response.status_code, 400)
        interpret.assert_not_called()

    @staticmethod
    def _cleaned_response():
        return {
            "task": "new_brand_naming",
            "search_mode": "new_brand",
            "entity_type": "автомобільні колеса",
            "brand_name": "",
            "brand_lock": "new",
            "website_urls": [],
            "owned_resources": [],
            "inferred_requested_resources": ["instagram"],
            "selected_resources": ["instagram"],
            "semantic_brief": "Новий бренд для автомобільних коліс.",
            "core_concepts": ["колеса", "рух"],
            "secondary_concepts": ["дорога"],
            "metaphor_directions": ["обертання"],
            "naming_roots": ["wheel", "motion", "grip"],
            "brand_traits": ["надійний"],
            "audience": [],
            "market": [],
            "languages": [],
            "avoid_words": [],
            "avoid_suffixes": [],
            "avoid_styles": [],
            "literal_non_seed_words": ["до", "машин"],
            "confidence": "high",
            "clarification_needed": False,
            "clarification_question": "",
        }

    @staticmethod
    def _intent(**overrides):
        value = {
            "task": "new_brand_naming",
            "search_mode": "new_brand",
            "entity_type": "автосервіс",
            "brand_name": "",
            "brand_lock": "new",
            "website_urls": [],
            "owned_resources": [],
            "inferred_requested_resources": [],
            "semantic_brief": "Створити новий бренд.",
            "core_concepts": ["ремонт", "рух"],
            "secondary_concepts": ["надійність"],
            "metaphor_directions": ["механічна точність"],
            "naming_roots": ["repair", "motion", "craft"],
            "brand_traits": ["надійний"],
            "audience": [],
            "market": [],
            "languages": [],
            "avoid_words": [],
            "avoid_suffixes": [],
            "avoid_styles": [],
            "literal_non_seed_words": ["хочу", "знайди", "назву"],
            "confidence": "high",
            "clarification_needed": False,
            "clarification_question": "",
        }
        value.update(overrides)
        return value


if __name__ == "__main__":
    unittest.main()
