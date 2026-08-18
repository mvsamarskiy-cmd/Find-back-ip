import unittest
from unittest.mock import patch

import app


class SearchIntentApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    @patch("app.trademark_links", return_value={})
    @patch("app.generate_ai_names", return_value=[{
        "name": "LemonClub",
        "reason": "Варіант для існуючого бренду",
        "pronunciation": "LEH-mon club",
        "language_risks": [],
    }])
    def test_fixed_existing_brand_can_search_without_project_brief(
        self, generate_ai_names, _trademark_links
    ):
        response = self.client.post(
            "/api/ai-names",
            json={
                "search_context": {
                    "mode": "existing_brand_fixed",
                    "brand_name": "Lemon",
                    "guidance": "Не використовуй official",
                }
            },
            environ_base={"REMOTE_ADDR": "198.51.100.71"},
        )
        self.assertEqual(response.status_code, 200)
        generate_ai_names.assert_called_once_with(
            "",
            10,
            {"liked": [], "disliked": [], "reasons": {}},
            search_context={
                "mode": "existing_brand_fixed",
                "brand_name": "Lemon",
                "guidance": "Не використовуй official",
            },
        )

    @patch("app.generate_ai_names")
    def test_existing_brand_mode_requires_brand_name(self, generate_ai_names):
        response = self.client.post(
            "/api/ai-names",
            json={"search_context": {"mode": "existing_brand_fixed"}},
            environ_base={"REMOTE_ADDR": "198.51.100.72"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("require a brand name", response.get_json()["error"])
        generate_ai_names.assert_not_called()

    @patch("app.generate_ai_names")
    def test_unknown_search_mode_is_rejected_before_ai(self, generate_ai_names):
        response = self.client.post(
            "/api/ai-names",
            json={
                "brief": "Новий бренд",
                "search_context": {"mode": "magic"},
            },
            environ_base={"REMOTE_ADDR": "198.51.100.73"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["allowed_search_modes"],
            list(app.SEARCH_MODES),
        )
        generate_ai_names.assert_not_called()

    @patch("app.generate_ai_names")
    def test_new_brand_still_requires_brief_or_brand_dna(self, generate_ai_names):
        response = self.client.post(
            "/api/ai-names",
            json={"search_context": {"mode": "new_brand"}},
            environ_base={"REMOTE_ADDR": "198.51.100.74"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Brief or Brand DNA", response.get_json()["error"])
        generate_ai_names.assert_not_called()

    def test_home_exposes_search_intent_and_guidance_controls(self):
        response = self.client.get("/")
        body = response.get_data(as_text=True)
        self.assertIn('id="searchMode"', body)
        self.assertIn('id="brandName"', body)
        self.assertIn('id="guidance"', body)
        self.assertIn("Бренд уже є — назва зафіксована", body)
        self.assertIn("Додаткові побажання", body)
        self.assertIn("Чому не подобається", body)
        self.assertIn("Надто банально", body)
        self.assertIn("Не подобається закінчення", body)


if __name__ == "__main__":
    unittest.main()
