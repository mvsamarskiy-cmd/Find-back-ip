import unittest
from unittest.mock import patch

import app


class AdaptiveSearchApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    @patch("app.trademark_links", return_value={})
    @patch("app.check_many", return_value=[{
        "availability": {"telegram": {"status": "not_found"}},
        "selected_resources": ["telegram"],
        "total_resources": 1,
    }])
    @patch("app.generate_ai_names", return_value=[{
        "name": "Klykno",
        "reason": "Нове семантичне поле",
        "pronunciation": "KLIK-no",
        "language_risks": [],
    }])
    def test_ai_generate_forwards_bounded_generation_context(
        self, generate_ai_names, _check_many, _trademark
    ):
        response = self.client.post(
            "/api/ai-generate",
            json={
                "brief": "Новий бренд спільноти",
                "count": 1,
                "resources": ["telegram"],
                "required_resources": ["telegram"],
                "generation_context": {
                    "batch_number": 2,
                    "exclude_names": ["Pryvia"],
                    "conflict_names": ["Pryvia"],
                    "successful_names": ["Nuvexa"],
                },
            },
            environ_base={"REMOTE_ADDR": "198.51.100.91"},
        )
        self.assertEqual(response.status_code, 200)
        generate_ai_names.assert_called_once_with(
            "Новий бренд спільноти",
            1,
            {"liked": [], "disliked": [], "reasons": {}},
            generation_context={
                "batch_number": 2,
                "exclude_names": ["Pryvia"],
                "conflict_names": ["Pryvia"],
                "successful_names": ["Nuvexa"],
            },
        )
        self.assertEqual(response.get_json()[0]["bundle_state"], "promising")

    @patch("app.generate_ai_names")
    def test_invalid_generation_context_is_rejected_before_ai(self, generate_ai_names):
        response = self.client.post(
            "/api/ai-generate",
            json={
                "brief": "Новий бренд",
                "resources": ["telegram"],
                "generation_context": ["bad"],
            },
            environ_base={"REMOTE_ADDR": "198.51.100.92"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("generation_context", response.get_json()["error"])
        generate_ai_names.assert_not_called()


if __name__ == "__main__":
    unittest.main()
