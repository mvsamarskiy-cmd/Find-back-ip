import unittest
from unittest.mock import patch

import app


class IdentityBundleApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    @patch("app.check_all", return_value={
        "availability": {
            "com": {"status": "claimable"},
            "telegram": {"status": "taken"},
        }
    })
    def test_check_classifies_only_required_subset(self, check_all):
        response = self.client.get(
            "/api/check/lemon?resources=com,telegram&required=com",
            environ_base={"REMOTE_ADDR": "198.51.100.81"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["bundle_state"], "confirmed")
        self.assertEqual(body["required_resources"], ["com"])
        check_all.assert_called_once_with("lemon", ("com", "telegram"))

    @patch("app.check_all")
    def test_required_resource_must_also_be_selected(self, check_all):
        response = self.client.get(
            "/api/check/lemon?resources=telegram&required=com",
            environ_base={"REMOTE_ADDR": "198.51.100.82"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("must also be selected", response.get_json()["error"])
        check_all.assert_not_called()

    @patch("app.check_all", return_value={
        "availability": {
            "instagram": {"status": "not_found"},
        }
    })
    def test_not_found_required_social_is_promising_not_free(self, _check_all):
        response = self.client.get(
            "/api/check/lemon?resources=instagram&required=instagram",
            environ_base={"REMOTE_ADDR": "198.51.100.83"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["bundle_state"], "promising")
        self.assertEqual(body["bundle_promising"], ["instagram"])


if __name__ == "__main__":
    unittest.main()
