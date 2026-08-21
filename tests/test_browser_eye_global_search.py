import os
import unittest
from unittest.mock import patch

from flask import Flask

from browser_eye_global_search import install_browser_global_search, normalize_serp_rows


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

    def test_web_search_route_requires_dedicated_token(self):
        app = Flask(__name__)
        app.testing = True
        install_browser_global_search(app, DummyRuntime())
        with patch.dict(os.environ, {"GLOBAL_SEARCH_BROWSER_TOKEN": "secret-token"}, clear=False):
            response = app.test_client().post("/v1/web-search", json={"query": "grants"})
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
