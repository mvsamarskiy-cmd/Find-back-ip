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
    def test_result_has_auditable_evidence_fields(self):
        result = availability._result("unknown", "test", "https://example.test")
        self.assertEqual(result["claimability"], "unconfirmed")
        self.assertEqual(result["occupancy"], "unknown")
        self.assertIn("checked_at", result)
        self.assertIn("confidence", result)

    def test_result_accepts_complete_status_vocabulary(self):
        self.assertEqual(
            {
                availability._result(status, "test", "https://example.test")["status"]
                for status in availability.STATUS_VALUES
            },
            set(availability.STATUS_VALUES),
        )
        with self.assertRaises(ValueError):
            availability._result("available", "legacy", "https://example.test")

    def test_result_derives_evidence_dimensions(self):
        not_found = availability._result(
            "not_found", "test", "https://example.test"
        )
        claimable = availability._result(
            "claimable", "test", "https://example.test"
        )
        self.assertEqual(not_found["occupancy"], "not_found")
        self.assertEqual(not_found["claimability"], "unconfirmed")
        self.assertEqual(claimable["claimability"], "confirmed")

    @patch("availability.requests.get", return_value=response(404))
    def test_com_404_is_not_found_not_claimable(self, _get):
        result = availability.check_com("Example")
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["claimability"], "unconfirmed")

    @patch("availability.requests.get", return_value=response(200))
    def test_com_200_is_taken(self, _get):
        self.assertEqual(availability.check_com("Example")["status"], "taken")

    @patch("availability.requests.get", return_value=response(200, "login page"))
    def test_instagram_generic_200_is_unknown(self, _get):
        self.assertEqual(availability.check_instagram("Example")["status"], "unknown")

    @patch("availability.requests.get", return_value=response(404))
    def test_instagram_404_does_not_claim_availability(self, _get):
        self.assertEqual(availability.check_instagram("Example")["status"], "not_found")

    @patch("availability.requests.get", return_value=response(429))
    def test_instagram_429_is_rate_limited(self, _get):
        self.assertEqual(availability.check_instagram("Example")["status"], "rate_limited")

    @patch("availability.requests.get", return_value=response(404))
    def test_tiktok_404_does_not_claim_availability(self, _get):
        self.assertEqual(availability.check_tiktok("Mova")["status"], "not_found")

    @patch(
        "availability.requests.get",
        return_value=response(200, "Couldn't find this account"),
    )
    def test_tiktok_missing_marker_does_not_claim_availability(self, _get):
        self.assertEqual(availability.check_tiktok("Mova")["status"], "not_found")

    @patch("availability.requests.get", return_value=response(404))
    def test_youtube_404_does_not_claim_availability(self, _get):
        self.assertEqual(availability.check_youtube("Yuno")["status"], "not_found")

    @patch("availability.requests.get", return_value=response(404))
    def test_x_404_does_not_claim_availability(self, _get):
        self.assertEqual(availability.check_x("Example")["status"], "not_found")

    @patch.dict("availability.os.environ", {"YOUTUBE_API_KEY": "test"}, clear=False)
    @patch("availability.requests.get")
    def test_youtube_official_lookup_confirms_occupied(self, get):
        official = response(200)
        official.json = lambda: {"items": [{"id": "channel"}]}
        get.return_value = official
        result = availability.check_youtube("Yuno")
        self.assertEqual(result["status"], "taken")
        self.assertEqual(result["source"], "youtube_data_api")
        self.assertEqual(result["confidence"], 0.99)

    @patch.dict("availability.os.environ", {"X_BEARER_TOKEN": "test"}, clear=False)
    @patch("availability.requests.get")
    def test_x_official_lookup_confirms_occupied(self, get):
        official = response(200)
        official.json = lambda: {"data": {"id": "user"}}
        get.return_value = official
        result = availability.check_x("Example")
        self.assertEqual(result["status"], "taken")
        self.assertEqual(result["source"], "x_api")

    @patch.dict("availability.os.environ", {"X_BEARER_TOKEN": "test"}, clear=False)
    @patch("availability.requests.get", return_value=response(429))
    def test_x_official_rate_limit_is_not_hidden_by_public_fallback(self, get):
        result = availability.check_x("Example")
        self.assertEqual(result["status"], "rate_limited")
        self.assertEqual(result["source"], "x_api")
        get.assert_called_once()

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
        claimable = {"status": "claimable"}
        unknown = {"status": "unknown"}
        with (
            patch("availability.check_com", return_value=claimable),
            patch("availability.check_instagram", return_value=claimable),
            patch("availability.check_telegram", return_value=unknown),
            patch("availability.check_tiktok", return_value=unknown),
            patch("availability.check_youtube", return_value=unknown),
            patch("availability.check_facebook", return_value=unknown),
            patch("availability.check_x", return_value=unknown),
        ):
            result = availability.check_all("Example")
        self.assertFalse(result["all_available"])
        self.assertFalse(result["all_verified"])
        self.assertEqual(result["claimable_count"], 2)
        self.assertEqual(result["available_count"], 2)
        self.assertEqual(result["not_found_count"], 0)
        self.assertEqual(result["unresolved_count"], 5)

    def test_not_found_is_rankable_evidence_but_not_availability(self):
        statuses = iter((
            "claimable",
            "purchasable",
            "not_found",
            "not_found",
            "taken",
            "rate_limited",
            "unknown",
        ))
        results = [{"status": next(statuses)} for _ in range(7)]
        with (
            patch("availability.check_com", return_value=results[0]),
            patch("availability.check_instagram", return_value=results[1]),
            patch("availability.check_telegram", return_value=results[2]),
            patch("availability.check_tiktok", return_value=results[3]),
            patch("availability.check_youtube", return_value=results[4]),
            patch("availability.check_facebook", return_value=results[5]),
            patch("availability.check_x", return_value=results[6]),
        ):
            result = availability.check_all("Example")
        self.assertEqual(result["actionable_count"], 2)
        self.assertEqual(result["available_count"], 2)
        self.assertEqual(result["not_found_count"], 2)
        self.assertEqual(result["rate_limited_count"], 1)
        self.assertEqual(result["unknown_count"], 1)
        self.assertEqual(result["unresolved_count"], 2)
        self.assertFalse(result["all_verified"])

    def test_check_all_contains_one_checker_crash(self):
        claimable = {"status": "claimable"}
        with (
            patch("availability.check_com", side_effect=RuntimeError("boom")),
            patch("availability.check_instagram", return_value=claimable),
            patch("availability.check_telegram", return_value=claimable),
            patch("availability.check_tiktok", return_value=claimable),
            patch("availability.check_youtube", return_value=claimable),
            patch("availability.check_facebook", return_value=claimable),
            patch("availability.check_x", return_value=claimable),
        ):
            result = availability.check_all("Example")
        self.assertEqual(result["availability"]["com"]["status"], "unknown")
        self.assertEqual(result["availability"]["com"]["method"], "checker_error")
        self.assertEqual(result["unknown_count"], 1)


if __name__ == "__main__":
    unittest.main()
