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

