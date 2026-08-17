import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch

try:
    import requests
except ModuleNotFoundError:
    class RequestException(Exception):
        pass

    class Timeout(RequestException):
        pass

    requests = SimpleNamespace(
        RequestException=RequestException,
        Timeout=Timeout,
        get=lambda *args, **kwargs: None,
    )
    sys.modules["requests"] = requests

import availability


def response(status_code, text=""):
    return SimpleNamespace(status_code=status_code, text=text)


class AvailabilityTests(unittest.TestCase):
    @patch("availability.requests.get", return_value=response(404))
    def test_com_404_is_available(self, _get):
        self.assertEqual(availability.check_com("Example")["status"], "available")

    @patch("availability.requests.get", return_value=response(200))
    def test_com_200_is_taken(self, _get):
        self.assertEqual(availability.check_com("Example")["status"], "taken")

    @patch("availability.requests.get", return_value=response(200, "login page"))
    def test_instagram_generic_200_is_unknown(self, _get):
        self.assertEqual(availability.check_instagram("Example")["status"], "unknown")

    @patch(
        "availability.requests.get",
        return_value=response(200, '<script>{"username":"example"}</script>'),
    )
    def test_instagram_matching_profile_is_taken(self, _get):
        self.assertEqual(availability.check_instagram("Example")["status"], "taken")

    @patch("availability.requests.get", side_effect=requests.Timeout("timeout"))
    def test_network_error_is_unknown(self, _get):
        self.assertEqual(availability.check_com("Example")["status"], "unknown")

    def test_check_all_aggregates_status(self):
        available = {"status": "available"}
        unknown = {"status": "unknown"}
        with (
            patch("availability.check_com", return_value=available),
            patch("availability.check_instagram", return_value=available),
            patch("availability.check_telegram", return_value=unknown),
            patch("availability.check_tiktok", return_value=unknown),
            patch("availability.check_youtube", return_value=unknown),
            patch("availability.check_facebook", return_value=unknown),
            patch("availability.check_x", return_value=unknown),
        ):
            result = availability.check_all("Example")
        self.assertFalse(result["all_available"])
        self.assertFalse(result["all_verified"])


if __name__ == "__main__":
    unittest.main()
