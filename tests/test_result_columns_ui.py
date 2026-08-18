import unittest

import app


class ResultColumnsUiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_home_has_required_resource_controls_and_result_columns(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn('name="requiredResource" value="com"', body)
        self.assertIn('name="requiredResource" value="telegram"', body)
        self.assertIn("Обов’язково мати (MUST HAVE)", body)
        self.assertIn('id="conflictGrid"', body)
        self.assertIn('id="opportunityGrid"', body)
        self.assertIn('id="unresolvedGrid"', body)
        self.assertIn("🔴 Конфлікти", body)
        self.assertIn("🟢 Придатні / перспективні", body)

    def test_each_main_column_has_its_own_resource_filter(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="conflictResourceFilter"', body)
        self.assertIn('id="opportunityResourceFilter"', body)
        self.assertIn('id="opportunityStateFilter"', body)
        self.assertIn("✓ Підтверджені", body)
        self.assertIn("◌ Перспективні", body)

    def test_ui_never_calls_not_found_confirmed_free(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("NOT FOUND", body)
        self.assertIn("перспективні", body.lower())
        self.assertIn("не підтверджує можливість реєстрації", body)
        self.assertNotIn("NOT FOUND = ВІЛЬНИЙ", body)

    def test_check_requests_send_required_resources(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("&required=", body)
        self.assertIn("requiredResources:required", body)
        self.assertIn("bundle_state", body)


if __name__ == "__main__":
    unittest.main()
