import os
import unittest
from unittest.mock import patch

from universal_search import (
    classify_search_route,
    infer_general_intent,
    search_general_web,
    search_module_web,
    search_universal,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"{}"

    def json(self):
        return self._payload


class UniversalSearchTests(unittest.TestCase):
    def test_company_query_does_not_inherit_eu_opportunity_bias(self):
        decision = classify_search_route(
            "Хто зараз CEO компанії Nvidia і коли його призначили?"
        )
        self.assertEqual(decision["route"], "company")
        self.assertEqual(decision["routed_category"], "all")
        self.assertEqual(decision["reason"], "high_confidence_research_module")

    def test_ambiguous_investment_query_stays_general(self):
        decision = classify_search_route("What is investment banking?")
        self.assertEqual(decision["route"], "general_web")

    def test_opportunity_query_uses_specialized_lane(self):
        decision = classify_search_route(
            "Знайди гранти для стартапу в Польщі"
        )
        self.assertEqual(decision["route"], "opportunity")
        self.assertEqual(decision["routed_category"], "grant")
        self.assertEqual(
            decision["reason"], "high_confidence_opportunity_intent"
        )

    def test_explicit_category_overrides_auto_router(self):
        decision = classify_search_route(
            "покажи цікаві речі", category="challenge"
        )
        self.assertEqual(decision["route"], "opportunity")
        self.assertEqual(decision["routed_category"], "challenge")
        self.assertEqual(decision["reason"], "explicit_category")

    def test_general_intent_is_auditable_but_does_not_change_truth_semantics(self):
        self.assertEqual(
            infer_general_intent("Порівняй PostgreSQL та MySQL"),
            "comparison",
        )
        self.assertEqual(
            infer_general_intent("latest Nvidia news today"),
            "current",
        )

    def test_general_web_search_sends_exact_query_once_to_browser_eye(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(200, {
                "provider_status": "complete",
                "results": [{
                    "title": "Photosynthesis overview",
                    "description": "A general reference page",
                    "url": "https://example.org/photosynthesis",
                }],
            })

        env = {
            "BRAVE_SEARCH_API_KEY": "",
            "BROWSER_EYE_URL": "http://browser-eye.internal",
            "GLOBAL_SEARCH_BROWSER_TOKEN": "test-browser-token",
        }
        query = "Explain photosynthesis"
        with patch.dict(os.environ, env, clear=False):
            payload = search_general_web(query, poster=fake_post)

        self.assertEqual(payload["intelligence_route"], "general_web")
        self.assertEqual(payload["search_plan"], [query])
        self.assertEqual(payload["provider"], "browser_eye_web")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["json"]["query"], query)
        self.assertNotIn("European Union", calls[0][1]["json"]["query"])
        self.assertNotIn("grant", calls[0][1]["json"]["query"].lower())
        self.assertTrue(payload["results"])

    def test_module_search_expands_only_when_exact_query_is_sparse(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs["json"]["query"])
            if len(calls) == 1:
                rows = [{
                    "title": "Python 3.14 release notes",
                    "description": "Release overview",
                    "url": "https://example.org/python-314",
                }]
            else:
                rows = [{
                    "title": "Python 3.14 documentation",
                    "description": "Official Python documentation",
                    "url": "https://docs.python.org/3.14/whatsnew/3.14.html",
                }]
            return FakeResponse(200, {"provider_status": "complete", "results": rows})

        env = {
            "BRAVE_SEARCH_API_KEY": "",
            "BROWSER_EYE_URL": "http://browser-eye.internal",
            "GLOBAL_SEARCH_BROWSER_TOKEN": "test-browser-token",
        }
        query = "Python 3.14 release notes"
        with patch.dict(os.environ, env, clear=False):
            payload = search_module_web(query, route="technical", poster=fake_post)

        self.assertEqual(payload["intelligence_route"], "technical")
        self.assertEqual(len(calls), 2)
        self.assertEqual(payload["search_plan"][0], query)
        self.assertIn("official documentation", payload["search_plan"][1])
        official_docs = [row for row in payload["results"] if row["host"] == "docs.python.org"]
        self.assertTrue(official_docs)
        self.assertTrue(official_docs[0]["preferred_source_match"])
        self.assertFalse(official_docs[0]["official_source"])
        self.assertIn("not verified facts", payload["truth_note"])

    def test_universal_router_does_not_call_specialized_routes_for_generic_query(self):
        calls = []

        def should_not_run(*_args, **_kwargs):
            raise AssertionError("specialized search must not run")

        def fake_general(query, **_kwargs):
            calls.append(query)
            return {
                "query": query,
                "provider_status": "complete",
                "results": [],
                "search_plan": [query],
                "intelligence_version": "general-web-v1",
            }

        payload = search_universal(
            "Explain photosynthesis",
            opportunity_searcher=should_not_run,
            module_searcher=should_not_run,
            general_searcher=fake_general,
        )
        self.assertEqual(calls, ["Explain photosynthesis"])
        self.assertEqual(payload["intelligence_route"], "general_web")
        self.assertEqual(payload["route_reason"], "no_specialized_intent")
        self.assertFalse(payload["intent_routed"])

    def test_universal_router_calls_module_for_technical_query(self):
        calls = []

        def fake_module(query, **kwargs):
            calls.append((query, kwargs))
            return {
                "query": query,
                "provider_status": "complete",
                "results": [],
                "search_plan": [query],
                "intelligence_version": "technical-v1",
            }

        def should_not_run(*_args, **_kwargs):
            raise AssertionError("wrong search lane")

        payload = search_universal(
            "Python 3.14 release notes",
            opportunity_searcher=should_not_run,
            general_searcher=should_not_run,
            module_searcher=fake_module,
        )
        self.assertEqual(payload["intelligence_route"], "technical")
        self.assertEqual(calls[0][1]["route"], "technical")
        self.assertEqual(payload["route_reason"], "high_confidence_research_module")
        self.assertTrue(payload["intent_routed"])

    def test_universal_router_calls_opportunity_for_grant_query(self):
        calls = []

        def fake_opportunity(query, **kwargs):
            calls.append((query, kwargs))
            return {
                "query": query,
                "provider_status": "complete",
                "results": [],
                "intelligence_version": "opportunity-v1",
            }

        def should_not_run(*_args, **_kwargs):
            raise AssertionError("non-opportunity search must not run")

        payload = search_universal(
            "Знайди гранти для AI стартапу",
            country="PL",
            opportunity_searcher=fake_opportunity,
            general_searcher=should_not_run,
            module_searcher=should_not_run,
        )
        self.assertEqual(payload["intelligence_route"], "opportunity")
        self.assertEqual(payload["routed_category"], "grant")
        self.assertEqual(calls[0][1]["category"], "grant")
        self.assertEqual(calls[0][1]["country"], "PL")


if __name__ == "__main__":
    unittest.main()
