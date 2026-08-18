from unittest import TestCase
from unittest.mock import Mock, patch

from verification.providers import instagram_web_adapter


class InstagramWebAdapterTests(TestCase):
    def _response(self, status, payload=None):
        response = Mock()
        response.status_code = status
        if payload is not None:
            response.json.return_value = payload
        return response

    @patch("verification.providers.instagram_web_adapter.requests.get")
    def test_exact_username_is_exists(self, get):
        get.return_value = self._response(200, {"data": {"user": {"username": "nike"}}})
        row = instagram_web_adapter.check_username("Nike")
        self.assertEqual(row["signal"], "exists")
        self.assertEqual(row["source"], "instagram_web_profile_info")
        self.assertEqual(row["http_status"], 200)

    @patch("verification.providers.instagram_web_adapter.requests.get")
    def test_404_is_absent_not_claimable(self, get):
        get.return_value = self._response(404)
        row = instagram_web_adapter.check_username("rarehandle")
        self.assertEqual(row["signal"], "absent")
        self.assertNotEqual(row["signal"], "claimable")
        self.assertFalse(row["metadata"]["authoritative_claimability"])

    @patch("verification.providers.instagram_web_adapter.requests.get")
    def test_gated_response_is_unknown(self, get):
        get.return_value = self._response(400)
        row = instagram_web_adapter.check_username("natgeo")
        self.assertEqual(row["signal"], "unknown")
        self.assertEqual(row["http_status"], 400)

    def test_other_platform_fails_closed(self):
        row = instagram_web_adapter.check_username("example", "x")
        self.assertEqual(row["signal"], "unknown")
