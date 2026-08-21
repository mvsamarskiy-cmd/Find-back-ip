import asyncio
import os
import unittest
from unittest.mock import patch

from flask import Flask

from browser_eye_global_search import (
    SEARCH_ENGINES,
    _search_async,
    classify_browser_error,
    install_browser_global_search,
    normalize_serp_rows,
)


class DummyRuntime:
    def _ensure_started(self):
        raise RuntimeError("browser not started in unit test")


class BrowserEyeGlobalSearchTests(unittest.TestCase):
    def test_google_redirect_is_unwrapped_and_rows_are_deduplicated(self):
        rows = normalize_serp_rows([
            {
                "title": "EU Funding & Tenders Portal",
                "url": "https://www.google.com/url?q=https%3A%2F%2Ffunding-tenders.ec.europa.eu%2Fportal%2Fscreen%2Fopportunities%2Ftopic-search&sa=U",
                "snippet": "Official portal",
            },
            {
                "title": "Duplicate",
                "url": "https://funding-tenders.ec.europa.eu/portal/screen/opportunities/topic-search",
                "snippet": "Same URL",
            },
            {
                "title": "Google internal",
                "url": "https://www.google.com/search?q=foo",
                "snippet": "Ignore",
            },
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["host"], "funding-tenders.ec.europa.eu")
        self.assertTrue(rows[0]["url"].startswith("https://funding-tenders.ec.europa.eu/"))

    def test_duckduckgo_redirect_is_unwrapped(self):
        rows = normalize_serp_rows([
            {
                "title": "PARP call",
                "url": "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.parp.gov.pl%2Fcomponent%2Fgrants%2Fgrants%2Fexample",
                "snippet": "Official programme",
            }
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["host"], "parp.gov.pl")

    def test_failover_moves_from_google_error_to_bing_success(self):
        calls = []

        async def scenario():
            class Runtime:
                pass

            runtime = Runtime()
            runtime._semaphores = {"search": asyncio.Semaphore(1)}

            async def fake_searcher(_runtime, engine, _query, _limit):
                calls.append(engine)
                if engine == "google":
                    return {
                        "engine": engine,
                        "provider_status": "error",
                        "results": [],
                        "error_stage": "goto",
                        "error_code": "navigation_failed",
                        "error_type": "Error",
                        "latency_ms": 50,
                    }
                if engine == "bing":
                    return {
                        "engine": engine,
                        "provider_status": "complete",
                        "results": [{
                            "title": "EU grant",
                            "url": "https://funding-tenders.ec.europa.eu/example",
                            "host": "funding-tenders.ec.europa.eu",
                            "description": "Open call",
                        }],
                        "captcha": False,
                        "latency_ms": 80,
                    }
                raise AssertionError("DuckDuckGo should not run after Bing succeeds")

            return await _search_async(runtime, "AI grants", 5, engine_searcher=fake_searcher)

        payload = asyncio.run(scenario())
        self.assertEqual(calls, ["google", "bing"])
        self.assertEqual(payload["provider_status"], "complete")
        self.assertEqual(payload["engine"], "bing")
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["attempts"][0]["error_code"], "navigation_failed")

    def test_engine_order_is_explicit_and_stable(self):
        self.assertEqual(SEARCH_ENGINES, ("google", "bing", "duckduckgo"))

    def test_browser_error_classifier_does_not_return_raw_message(self):
        error = RuntimeError("Page.goto: net::ERR_FAILED at https://secret.example/search?q=sensitive")
        code = classify_browser_error(error)
        self.assertEqual(code, "navigation_failed")
        self.assertNotIn("secret.example", code)
        self.assertNotIn("sensitive", code)

    def test_web_search_route_requires_dedicated_token(self):
        app = Flask(__name__)
        app.testing = True
        install_browser_global_search(app, DummyRuntime())
        with patch.dict(os.environ, {"GLOBAL_SEARCH_BROWSER_TOKEN": "secret-token"}, clear=False):
            response = app.test_client().post("/v1/web-search", json={"query": "grants"})
        self.assertEqual(response.status_code, 401)

    def test_wrong_dedicated_token_is_rejected(self):
        app = Flask(__name__)
        app.testing = True
        install_browser_global_search(app, DummyRuntime())
        with patch.dict(os.environ, {"GLOBAL_SEARCH_BROWSER_TOKEN": "secret-token"}, clear=False):
            response = app.test_client().post(
                "/v1/web-search",
                json={"query": "grants"},
                headers={"X-Global-Search-Token": "wrong-token"},
            )
        self.assertEqual(response.status_code, 401)

    def test_missing_server_token_fails_closed(self):
        app = Flask(__name__)
        app.testing = True
        install_browser_global_search(app, DummyRuntime())
        with patch.dict(os.environ, {"GLOBAL_SEARCH_BROWSER_TOKEN": ""}, clear=False):
            response = app.test_client().post(
                "/v1/web-search",
                json={"query": "grants"},
                headers={"X-Global-Search-Token": "anything"},
            )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
