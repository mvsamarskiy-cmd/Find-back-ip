import os
import unittest
from unittest.mock import patch

from multi_intent_planner import plan_research_routes
from universal_search_multi import (
    classify_search_plan,
    infer_general_intents,
    search_multi_module_web,
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


class MultiIntentPlannerTests(unittest.TestCase):
    def test_product_local_query_gets_two_routes_and_current_comparison_facets(self):
        query = (
            "Find 5 best laptops under 4000 zł in Warsaw, compare prices and "
            "tell me where to buy today"
        )
        decision = classify_search_plan(query)

        self.assertEqual(decision["route"], "multi")
        self.assertEqual(decision["primary_route"], "product")
        self.assertEqual(decision["routes"], ["product", "local"])
        self.assertTrue(decision["multi_intent"])
        self.assertIn("current", decision["general_intents"])
        self.assertIn("comparison", decision["general_intents"])

    def test_local_commerce_composition_works_in_ukrainian_polish_and_lowercase(self):
        ukrainian = plan_research_routes("де купити ноутбук у варшаві сьогодні")
        polish = plan_research_routes("gdzie kupić laptop w warszawie dzisiaj")
        english = plan_research_routes("where to buy laptop in warsaw today")

        self.assertEqual(ukrainian["routes"], ["product", "local"])
        self.assertEqual(polish["routes"], ["product", "local"])
        self.assertEqual(english["routes"], ["product", "local"])

    def test_price_by_country_without_physical_buy_intent_stays_product_only(self):
        decision = classify_search_plan("iPhone 17 price in Poland")
        self.assertEqual(decision["route"], "product")
        self.assertEqual(decision["routes"], ["product"])
        self.assertFalse(decision["multi_intent"])

    def test_explicit_current_technical_query_can_compose_news_and_technical(self):
        decision = classify_search_plan("Python 3.14 release notes latest news today")
        self.assertEqual(decision["route"], "multi")
        self.assertIn("technical", decision["routes"])
        self.assertIn("news", decision["routes"])
        self.assertLessEqual(len(decision["routes"]), 3)

    def test_product_local_and_explicit_news_can_form_bounded_triple(self):
        decision = classify_search_plan(
            "latest iPhone 17 news, where to buy in warsaw today"
        )
        self.assertEqual(decision["route"], "multi")
        self.assertEqual(set(decision["routes"]), {"product", "local", "news"})
        self.assertEqual(len(decision["routes"]), 3)

    def test_simple_ceo_query_does_not_fan_out_into_person_lane(self):
        decision = classify_search_plan("Who is the CEO of Nvidia?")
        self.assertEqual(decision["route"], "company")
        self.assertEqual(decision["routes"], ["company"])

    def test_general_facets_can_be_multi_without_creating_fake_news_route(self):
        facets = infer_general_intents("compare laptop prices today")
        self.assertIn("comparison", facets)
        self.assertIn("current", facets)
        decision = classify_search_plan("best price iPhone 17 today")
        self.assertEqual(decision["routes"], ["product"])

    def test_existing_false_positive_guards_survive_v3_composition(self):
        self.assertEqual(
            classify_search_plan("weather today in Warsaw")["route"],
            "general_web",
        )
        self.assertEqual(
            classify_search_plan("best price Bitcoin today")["route"],
            "general_web",
        )
        self.assertEqual(
            classify_search_plan("What is investment banking?")["route"],
            "general_web",
        )

    def test_opportunity_precedence_remains_single_lane(self):
        decision = classify_search_plan(
            "Знайди грант на купівлю обладнання для стартапу в Польщі"
        )
        self.assertEqual(decision["route"], "opportunity")
        self.assertEqual(decision["routes"], ["opportunity"])
        self.assertFalse(decision["multi_intent"])


class MultiIntentExecutionTests(unittest.TestCase):
    def test_exact_query_runs_once_and_expansions_are_bounded_per_route(self):
        calls = []

        def fake_post(_url, **kwargs):
            query = kwargs["json"]["query"]
            calls.append(query)
            if len(calls) == 1:
                rows = [{
                    "title": "Laptop offer",
                    "description": "Observed Warsaw offer",
                    "url": "https://example.org/laptop",
                }]
            elif "price availability" in query:
                rows = [{
                    "title": "Laptop price comparison",
                    "description": "Observed product result",
                    "url": "https://example.org/laptop",
                }]
            else:
                rows = [{
                    "title": "Warsaw laptop retailer",
                    "description": "Observed local result",
                    "url": "https://example.org/warsaw-store",
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
        query = "laptop in Warsaw compare prices where to buy today"
        with patch.dict(os.environ, env, clear=False):
            payload = search_multi_module_web(
                query,
                routes=["product", "local"],
                poster=fake_post,
            )

        self.assertEqual(calls[0], query)
        self.assertEqual(calls.count(query), 1)
        self.assertLessEqual(len(calls), 3)
        self.assertEqual(payload["intelligence_routes"], ["product", "local"])
        self.assertTrue(payload["multi_intent"])
        self.assertLessEqual(len(payload["search_plan"]), 3)
        self.assertEqual(len(payload["results"]), 2)
        duplicate = next(row for row in payload["results"] if row["url"] == "https://example.org/laptop")
        self.assertIn("shared", duplicate["evidence_lanes"])
        self.assertIn("product", duplicate["evidence_lanes"])
        self.assertIn("not verified prices", payload["truth_note"])

    def test_universal_executor_calls_multi_lane_only_for_multi_plan(self):
        calls = []

        def fake_multi(query, **kwargs):
            calls.append((query, list(kwargs["routes"])))
            return {
                "query": query,
                "provider_status": "complete",
                "results": [],
                "search_plan": [query],
                "intelligence_version": "multi-intent-v1",
            }

        def should_not_run(*_args, **_kwargs):
            raise AssertionError("wrong search lane")

        query = "laptop in Warsaw compare prices where to buy today"
        payload = search_universal(
            query,
            opportunity_searcher=should_not_run,
            general_searcher=should_not_run,
            module_searcher=should_not_run,
            multi_searcher=fake_multi,
        )

        self.assertEqual(calls, [(query, ["product", "local"])])
        self.assertEqual(payload["intelligence_route"], "product")
        self.assertEqual(payload["intelligence_routes"], ["product", "local"])
        self.assertTrue(payload["multi_intent"])

    def test_single_product_query_still_uses_existing_module_searcher(self):
        calls = []

        def fake_module(query, **kwargs):
            calls.append((query, kwargs["route"]))
            return {
                "query": query,
                "provider_status": "complete",
                "results": [],
                "search_plan": [query],
                "intelligence_version": "product-v1",
            }

        def should_not_run(*_args, **_kwargs):
            raise AssertionError("wrong search lane")

        payload = search_universal(
            "iPhone 17 price in Poland",
            opportunity_searcher=should_not_run,
            general_searcher=should_not_run,
            module_searcher=fake_module,
            multi_searcher=should_not_run,
        )

        self.assertEqual(calls, [("iPhone 17 price in Poland", "product")])
        self.assertEqual(payload["intelligence_routes"], ["product"])
        self.assertFalse(payload["multi_intent"])

    def test_capabilities_publish_bounded_multi_intent_contract(self):
        payload = universal_search_capabilities()
        self.assertEqual(payload["intelligence_version"], "universal-router-v3")
        self.assertTrue(payload["natural_language_multi_intent_planning"])
        self.assertEqual(payload["multi_intent"]["version"], "multi-intent-v1")
        self.assertEqual(payload["multi_intent"]["max_routes"], 3)
        self.assertEqual(payload["multi_intent"]["max_provider_queries"], 4)
        self.assertEqual(
            payload["multi_intent"]["truth_semantics"],
            "retrieval_evidence_not_verified_fact",
        )


if __name__ == "__main__":
    unittest.main()
