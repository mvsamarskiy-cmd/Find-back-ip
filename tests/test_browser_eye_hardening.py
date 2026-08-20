import unittest

import browser_eye_service as service
from browser_eye_hardening import install_browser_eye_hardening


class BrowserEyeHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_browser_eye_hardening(service)

    def test_requested_x_url_with_error_shell_is_not_occupancy(self):
        result = service.fingerprint_from_snapshot(
            "x",
            "sunriseposy",
            {
                "title": "X",
                "canonical": "https://x.com/sunriseposy",
                "final_url": "https://x.com/sunriseposy",
                "body_text": "Something went wrong. Try again.",
                "script_text": "",
                "og_image": "https://cdn.example/avatar.jpg",
            },
            [],
            engine="chromium",
            http_status=200,
        )
        self.assertEqual(result["signal"], "unknown")
        self.assertFalse(result["username_exact"])
        self.assertEqual(result["requested_handle"], "sunriseposy")
        self.assertEqual(result["identity_sources"], [])

    def test_exact_telegram_title_and_path_is_valid_identity(self):
        result = service.fingerprint_from_snapshot(
            "telegram",
            "sunriseposy",
            {
                "title": "Telegram: Contact @sunriseposy",
                "og_title": "Telegram: Contact @sunriseposy",
                "canonical": "https://t.me/sunriseposy",
                "final_url": "https://t.me/sunriseposy",
                "body_text": "If you have Telegram, you can contact @sunriseposy right away.",
                "script_text": "",
                "og_image": "https://cdn.example/avatar.jpg",
            },
            [],
            engine="webkit",
            http_status=200,
        )
        self.assertEqual(result["signal"], "exists")
        self.assertEqual(result["observed_username"], "sunriseposy")
        self.assertIn("telegram_exact_title_and_path", result["identity_sources"])

    def test_structured_different_username_fails_closed(self):
        result = service.fingerprint_from_snapshot(
            "instagram",
            "wantedname",
            {
                "title": "Wanted (@wantedname) • Instagram",
                "og_title": "Wanted (@wantedname) • Instagram",
                "canonical": "https://www.instagram.com/wantedname/",
                "final_url": "https://www.instagram.com/wantedname/",
                "body_text": "",
                "script_text": '{"username":"differentname","id":"123456"}',
                "og_image": "https://cdn.example/avatar.jpg",
            },
            [],
            engine="chromium",
            http_status=200,
        )
        self.assertEqual(result["signal"], "unknown")
        self.assertEqual(result["observed_username"], "differentname")

    def test_search_eye_requires_exact_profile_path(self):
        result = service.search_fingerprint(
            'site:x.com "torvex"',
            "torvex",
            "x",
            {
                "body_text": "results",
                "links": [
                    {"href": "https://x.com/torvex", "text": "Victor @torvex"},
                    {"href": "https://x.com/torvex2", "text": "Other"},
                    {"href": "https://x.com/foo/torvex", "text": "Nested"},
                ],
            },
        )
        self.assertEqual(result["exact_profile_hits"], 1)
        self.assertEqual(result["hits"][0]["url"], "https://x.com/torvex")
        self.assertEqual(result["url_match_policy"], "exact_profile_path")


if __name__ == "__main__":
    unittest.main()
