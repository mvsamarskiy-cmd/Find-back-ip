import asyncio
import os
import unittest
from unittest.mock import patch

from flask import Flask

from browser_eye_tor import (
    TOR_SEARCH_ENGINES,
    install_browser_tor_routes,
    is_v3_onion_host,
    safe_tor_url,
    tor_search_async,
)


VALID_ONION = "a" * 56 + ".onion"


class DummyRuntime:
    def _ensure_started(self):
        raise RuntimeError("not expected")


class BrowserEyeTorTests(unittest.TestCase):
    def test_v3_onion_validation(self):
        self.assertTrue(is_v3_onion_host(VALID_ONION))
        self.assertFalse(is_v3_onion_host("abcdefghijklmnop.onion"))
        self.assertTrue(safe_tor_url("http://" + VALID_ONION + "/opportunity"))
        self.assertEqual(safe_tor_url("http://abcdefghijklmnop.onion/"), "")

    def test_url_guard_rejects_local_private_and_credentials(self):
        self.assertEqual(safe_tor_url("http://127.0.0.1/admin"), "")
        self.assertEqual(safe_tor_url("http://192.168.1.2/"), "")
        self.assertEqual(safe_tor_url("http://user:pass@example.com/"), "")
        self.assertEqual(safe_tor_url("file:///etc/passwd"), "")
        self.assertEqual(safe_tor_url("https://example.com/opportunity"), "https://example.com/opportunity")

    def test_search_order_is_explicit(self):
        self.assertEqual(TOR_SEARCH_ENGINES, ("duckduckgo", "bing", "google"))

    def test_tor_search_preserves_transport_and_failover(self):
        calls = []

        async def scenario():
            class Runtime:
                pass
            runtime = Runtime()
            runtime._semaphores = {"search": asyncio.Semaphore(1)}

            async def searcher(_runtime, engine, _query, _limit):
                calls.append(engine)
                if engine == "duckduckgo":
                    return {"engine": engine, "provider_status": "challenge", "results": [], "latency_ms": 10}
                return {
                    "engine": engine,
                    "provider_status": "complete",
                    "results": [{"title": "Local opportunity", "url": "https://example.com/call", "host": "example.com", "description": "Open call", "transport": "tor", "onion_service": False}],
                    "latency_ms": 20,
                }

            return await tor_search_async(runtime, "grant", 5, engine_searcher=searcher)

        payload = asyncio.run(scenario())
        self.assertEqual(calls, ["duckduckgo", "bing"])
        self.assertEqual(payload["transport"], "tor")
        self.assertEqual(payload["provider"], "browser_eye_tor_web")
        self.assertEqual(len(payload["results"]), 1)

    def test_routes_require_private_global_search_token(self):
        app = Flask(__name__)
        app.testing = True
        install_browser_tor_routes(app, DummyRuntime())
        with patch.dict(os.environ, {"GLOBAL_SEARCH_BROWSER_TOKEN": "secret", "TOR_SEARCH_ENABLED": "1"}, clear=False):
            response = app.test_client().post("/v1/tor-web-search", json={"query": "grants"})
        self.assertEqual(response.status_code, 401)

    def test_disabled_transport_fails_closed(self):
        app = Flask(__name__)
        app.testing = True
        install_browser_tor_routes(app, DummyRuntime())
        with patch.dict(os.environ, {"GLOBAL_SEARCH_BROWSER_TOKEN": "secret", "TOR_SEARCH_ENABLED": "0"}, clear=False):
            response = app.test_client().post(
                "/v1/tor-web-search",
                json={"query": "grants"},
                headers={"X-Global-Search-Token": "secret"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["provider_status"], "disabled")


if __name__ == "__main__":
    unittest.main()
