import unittest

import app


class ResultColumnsUiTests(unittest.TestCase):
    def setUp(self):
        self.body = app.app.test_client().get("/").get_data(as_text=True)

    def test_home_has_three_simple_workspaces(self):
        self.assertIn('id="recommendedGrid"', self.body)
        self.assertIn('id="feedGrid"', self.body)
        self.assertIn('id="shortlistGrid"', self.body)
        self.assertIn("Рекомендовані", self.body)
        self.assertIn("Стрічка", self.body)
        self.assertIn("Кандидати", self.body)
        self.assertNotIn("Обов’язково мати (MUST HAVE)", self.body)
        self.assertNotIn('name="requiredResource"', self.body)

    def test_recommended_requires_every_selected_resource_confirmed(self):
        self.assertIn("function allGreen(row)", self.body)
        self.assertIn("resources.every", self.body)
        self.assertIn("confirmedStatuses.has", self.body)
        self.assertIn("claimable", self.body)
        self.assertIn("purchasable", self.body)

    def test_not_found_is_not_called_free(self):
        self.assertIn("status==='not_found'", self.body)
        self.assertIn("Не знайдено", self.body)
        self.assertNotIn("NOT FOUND = ВІЛЬНИЙ", self.body)

    def test_feed_supports_explicit_learning_actions(self):
        self.assertIn("👍", self.body)
        self.assertIn("👎", self.body)
        self.assertIn("Коментар", self.body)
        self.assertIn("Взяти за напрям", self.body)
        self.assertIn("В кандидати", self.body)
        self.assertIn("function saveComment", self.body)
        self.assertIn("function takeDirection", self.body)
        self.assertIn("function toggleShortlist", self.body)


if __name__ == "__main__":
    unittest.main()
