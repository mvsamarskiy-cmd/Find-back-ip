import os
import unittest
from unittest.mock import patch

from universal_search import (
    classify_search_route,
    infer_general_intent,
    search_general_web,
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
    def test_generic_query_does_not_inherit_eu_opportunity_bias(self):
        decision = classify_search_route(
            "Хто зараз CEO компанії Nvidia і коли його призначили?"
        )
        self.assertEqual(decision["route"], "general_web")
        self.assertEqual(decision["routed_category"], "all")

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
                    "title": "NVIDIA leadership",
                    "description": "Official company leadership page",
                    "url": "https://www.nvidia.com/en-us/about-nvidia/leadership/",
                }],
            })

        env = {
            "BRAVE_SEARCH_API_KEY": "",
            "BROWSER_EYE_URL": "http://browser-eye.internal",
            "GLOBAL_SEARCH_BROWSER_TOKEN": "test-browser-token",
        }
        query = "Хто CEO Nvidia?"
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

    def test_universal_router_does_not_call_opportunity_for_generic_query(self):
        calls = []

        def should_not_run(*_args, **_kwargs):
            raise AssertionError("opportunity search must not run")

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
            "Python 3.14 release notes",
            opportunity_searcher=should_not_run,
            general_searcher=fake_general,
        )
        self.assertEqual(calls, ["Python 3.14 release notes"])
        self.assertEqual(payload["intelligence_route"], "general_web")
        self.assertEqual(payload["route_reason"], "no_specialized_intent")

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
            raise AssertionError("general search must not run")

        payload = search_universal(
            "Знайди гранти для AI стартапу",
            country="PL",
            opportunity_searcher=fake_opportunity,
            general_searcher=should_not_run,
        )
        self.assertEqual(payload["intelligence_route"], "opportunity")
        self.assertEqual(payload["routed_category"], "grant")
        self.assertEqual(calls[0][1]["category"], "grant")
        self.assertEqual(calls[0][1]["country"], "PL")


if __name__ == "__main__":
    unittest.main()
