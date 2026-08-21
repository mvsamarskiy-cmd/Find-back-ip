import os
import unittest
from unittest.mock import patch

from universal_search import (
    classify_search_route,
    search_module_web,
    search_universal,
    universal_search_capabilities,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"{}"

    def json(self):
        return self._payload


class ProductLocalIntegrationTests(unittest.TestCase):
    def test_router_selects_product_and_local_modules(self):
        product = classify_search_route("iPhone 17 price in Poland")
        local = classify_search_route("restaurants in Warsaw")

        self.assertEqual(product["route"], "product")
        self.assertEqual(product["module_version"], "product-v1")
        self.assertEqual(local["route"], "local")
        self.assertEqual(local["module_version"], "local-v1")

    def test_opportunity_precedence_is_preserved(self):
        decision = classify_search_route(
            "Знайди грант на купівлю обладнання для стартапу в Польщі"
        )
        self.assertEqual(decision["route"], "opportunity")
        self.assertEqual(decision["routed_category"], "grant")

    def test_product_module_search_uses_bounded_second_query_and_ranking_only_affinity(self):
        calls = []

        def fake_post(_url, **kwargs):
            query = kwargs["json"]["query"]
            calls.append(query)
            if len(calls) == 1:
                rows = [{
                    "title": "iPhone 17 listing",
                    "description": "Observed listing without independent verification",
                    "url": "https://example.org/iphone-17",
                }]
            else:
                rows = [{
                    "title": "iPhone 17 price comparison",
                    "description": "Observed comparison result",
                    "url": "https://www.ceneo.pl/iphone-17",
                }]
            return FakeResponse(200, {
                "provider_status": "complete",
                "results": rows,
            })

        env = {
            "BRAVE_SEARCH_API_KEY": "",
            "BROWSER_EYE_URL": "http://browser-eye.internal",
            "GLOBAL_SEARCH_BROWSER_TOKEN": "test-browser-token",
        }
        with patch.dict(os.environ, env, clear=False):
            payload = search_module_web(
                "iPhone 17 price in Poland",
                route="product",
                poster=fake_post,
            )

        self.assertEqual(payload["intelligence_route"], "product")
        self.assertLessEqual(len(calls), 2)
        self.assertEqual(calls[0], "iPhone 17 price in Poland")
        ceneo = [row for row in payload["results"] if row["host"] == "ceneo.pl"]
        self.assertTrue(ceneo)
        self.assertTrue(ceneo[0]["preferred_source_match"])
        self.assertFalse(ceneo[0]["official_source"])
        self.assertIn("not verified facts", payload["truth_note"])

    def test_local_module_keeps_exact_place_query_and_does_not_claim_verification(self):
        calls = []

        def fake_post(_url, **kwargs):
            query = kwargs["json"]["query"]
            calls.append(query)
            rows = [{
                "title": "Restaurant listing",
                "description": "Observed local result",
                "url": "https://www.tripadvisor.com/Restaurant_Review-example",
            }]
            return FakeResponse(200, {
                "provider_status": "complete",
                "results": rows,
            })

        env = {
            "BRAVE_SEARCH_API_KEY": "",
            "BROWSER_EYE_URL": "http://browser-eye.internal",
            "GLOBAL_SEARCH_BROWSER_TOKEN": "test-browser-token",
        }
        with patch.dict(os.environ, env, clear=False):
            payload = search_module_web(
                "restaurants in Warsaw",
                route="local",
                poster=fake_post,
            )

        self.assertEqual(payload["intelligence_route"], "local")
        self.assertEqual(calls[0], "restaurants in Warsaw")
        self.assertTrue(payload["results"])
        self.assertFalse(payload["results"][0]["official_source"])

    def test_universal_search_calls_shared_module_transport(self):
        calls = []

        def fake_module(query, **kwargs):
            calls.append((query, kwargs["route"]))
            return {
                "query": query,
                "provider_status": "complete",
                "results": [],
                "search_plan": [query],
                "intelligence_version": f"{kwargs['route']}-v1",
            }

        def should_not_run(*_args, **_kwargs):
            raise AssertionError("wrong search lane")

        product_payload = search_universal(
            "best price iPhone 17 today",
            opportunity_searcher=should_not_run,
            general_searcher=should_not_run,
            module_searcher=fake_module,
        )
        local_payload = search_universal(
            "best hotels in Warsaw today",
            opportunity_searcher=should_not_run,
            general_searcher=should_not_run,
            module_searcher=fake_module,
        )

        self.assertEqual(product_payload["intelligence_route"], "product")
        self.assertEqual(local_payload["intelligence_route"], "local")
        self.assertEqual(calls, [
            ("best price iPhone 17 today", "product"),
            ("best hotels in Warsaw today", "local"),
        ])

    def test_capabilities_publish_new_routes(self):
        payload = universal_search_capabilities()
        self.assertIn("product", payload["routes"])
        self.assertIn("local", payload["routes"])
        self.assertEqual(payload["modules"]["product"]["version"], "product-v1")
        self.assertEqual(payload["modules"]["local"]["version"], "local-v1")


if __name__ == "__main__":
    unittest.main()
