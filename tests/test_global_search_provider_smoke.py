import os
import unittest
from unittest.mock import patch

from global_search_provider_smoke import maybe_start_provider_smoke, run_provider_smoke


class FakeResponse:
    status_code = 200
    content = b"{}"

    def json(self):
        return {
            "provider_status": "complete",
            "results": [
                {"title": "one", "url": "https://example.test/one"},
                {"title": "two", "url": "https://example.test/two"},
            ],
            "captcha": False,
            "latency_ms": 321,
        }


class GlobalSearchProviderSmokeTests(unittest.TestCase):
    def test_smoke_is_disabled_by_default(self):
        with patch.dict(os.environ, {"GLOBAL_SEARCH_STARTUP_SMOKE": ""}, clear=False):
            self.assertFalse(maybe_start_provider_smoke())

    def test_smoke_reports_sanitized_transport_metadata(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse()

        secret = "super-secret-provider-token"
        env = {
            "BROWSER_EYE_URL": "https://browser-eye.example.test",
            "GLOBAL_SEARCH_BROWSER_TOKEN": secret,
        }
        with patch.dict(os.environ, env, clear=False):
            result = run_provider_smoke(poster=fake_post)

        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["provider_status"], "complete")
        self.assertEqual(result["result_count"], 2)
        self.assertFalse(result["captcha"])
        self.assertEqual(result["latency_ms"], 321)
        self.assertNotIn(secret, repr(result))
        self.assertNotIn("browser-eye.example.test", repr(result))
        self.assertEqual(calls[0][1]["headers"]["X-Global-Search-Token"], secret)
        self.assertEqual(calls[0][1]["json"]["limit"], 3)

    def test_missing_config_fails_closed_without_request(self):
        def should_not_run(*_args, **_kwargs):
            raise AssertionError("poster must not be called")

        with patch.dict(
            os.environ,
            {"BROWSER_EYE_URL": "", "GLOBAL_SEARCH_BROWSER_TOKEN": ""},
            clear=False,
        ):
            result = run_provider_smoke(poster=should_not_run)

        self.assertFalse(result["configured"])
        self.assertEqual(result["provider_status"], "unconfigured")
        self.assertEqual(result["result_count"], 0)


if __name__ == "__main__":
    unittest.main()
