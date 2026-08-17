import unittest
from unittest.mock import patch

import app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_check_rejects_invalid_name(self):
        self.assertEqual(self.client.get("/api/check/12").status_code, 400)

    def test_generate_caps_count(self):
        with patch("app.generate", return_value=[]) as generate:
            self.client.get("/api/generate?count=999")
        generate.assert_called_once_with(40, False)

    def test_ai_requires_brief(self):
        self.assertEqual(self.client.post("/api/ai-generate", json={}).status_code, 400)

    def test_clean_preferences_bounds_and_sanitizes_feedback(self):
        result = app.clean_preferences({
            "liked": ["O'Miro", "Veya!"],
            "disliked": ["Bad Name"],
            "reasons": {"SOUND": 99, "bad-key!": -99, "broken": "no"},
        })
        self.assertEqual(result["liked"], ["omiro", "veya"])
        self.assertEqual(result["disliked"], ["badname"])
        self.assertEqual(result["reasons"], {"sound": 20, "badkey": -20})

    @patch("app.trademark_links", return_value={})
    @patch("app.generate_ai_names", return_value=[{
        "name": "Veya", "reason": "Причина", "pronunciation": "VEY-a",
        "language_risks": [],
    }])
    def test_ai_names_passes_project_preferences(self, generate_ai_names, _trademark_links):
        response = self.client.post("/api/ai-names", json={
            "brief": "Український бренд",
            "count": 5,
            "preferences": {"liked": ["Veya"], "disliked": ["Rovo"], "reasons": {"sound": 2}},
        })
        self.assertEqual(response.status_code, 200)
        generate_ai_names.assert_called_once_with(
            "Український бренд", 5,
            {"liked": ["veya"], "disliked": ["rovo"], "reasons": {"sound": 2}},
        )

    def test_home_contains_project_feedback_controls(self):
        response = self.client.get("/")
        body = response.get_data(as_text=True)
        self.assertIn("Профіль смаку", body)
        self.assertIn("Подобається", body)
        self.assertIn("projectSelect", body)
