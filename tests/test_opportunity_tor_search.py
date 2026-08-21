import unittest
from unittest.mock import patch

from opportunity_tor_search import opportunity_search_capabilities, search_global


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"{}"

    def json(self):
        return self._payload


class OpportunityTorSearchTests(unittest.TestCase):
    def _base_payload(self):
        return {
            "query": "grant for startup",
            "category": "grant",
            "country": "PL",
            "provider": "browser_eye_google",
            "provider_status": "complete",
            "results": [{
                "title": "Existing grant",
                "description": "Grant up to 10000 PLN",
                "url": "https://example.com/grant",
                "host": "example.com",
                "category": "grant",
                "retrieval_score": 70,
                "source_tier": "web",
                "source_name": "example.com",
                "source_country": None,
                "official_source": False,
                "query_index": 0,
            }],
        }

    @patch("opportunity_tor_search.base_search._provider_config")
    @patch("opportunity_tor_search.base_search.search_global")
    def test_exact_query_runs_once_over_tor_and_merges_new_evidence(self, base_search, provider_config):
        base_search.return_value = self._base_payload()
        provider_config.return_value = {
            "browser_eye": True,
            "browser_url": "https://browser.internal",
            "browser_token": "token",
            "brave": False,
        }
        calls = []

        def poster(url, **kwargs):
            calls.append((url, kwargs["json"]["query"]))
            return FakeResponse(payload={
                "provider_status": "complete",
                "results": [
                    {"title": "Existing duplicate", "description": "same", "url": "https://example.com/grant"},
                    {"title": "Tor discovered call", "description": "Open call 25000 PLN", "url": "https://hidden.example/call"},
                ],
            })

        result = search_global("grant for startup", category="grant", country="PL", poster=poster)
        self.assertEqual(calls, [("https://browser.internal/v1/tor-web-search", "grant for startup")])
        self.assertEqual(result["tor_retrieval"]["result_count"], 1)
        tor_rows = [row for row in result["results"] if row.get("transport") == "tor"]
        self.assertEqual(len(tor_rows), 1)
        self.assertFalse(tor_rows[0]["opportunity"]["verification"]["source_verified"])

    @patch("opportunity_tor_search.base_search._provider_config")
    @patch("opportunity_tor_search.base_search.search_global")
    def test_tor_failure_preserves_standard_results(self, base_search, provider_config):
        base_search.return_value = self._base_payload()
        provider_config.return_value = {
            "browser_eye": True,
            "browser_url": "https://browser.internal",
            "browser_token": "token",
            "brave": False,
        }

        def poster(url, **kwargs):
            return FakeResponse(status_code=503, payload={})

        result = search_global("grant for startup", category="grant", country="PL", poster=poster)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["tor_retrieval"]["provider_status"], "provider_http_503")

    def test_capabilities_never_infer_verification_from_tor(self):
        caps = opportunity_search_capabilities()["tor_retrieval"]
        self.assertTrue(caps["onion_service_evidence"])
        self.assertFalse(caps["verification_inferred_from_tor"])
        self.assertEqual(caps["exact_query_max_calls"], 1)


if __name__ == "__main__":
    unittest.main()
