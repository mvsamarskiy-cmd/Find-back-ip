import os
import unittest
from unittest.mock import patch

from search_query_quality import (
    apply_general_relevance_guard,
    looks_like_business_idea_query,
    repair_search_query,
    search_business_ideas,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"{}"

    def json(self):
        return self._payload


class QueryRepairTests(unittest.TestCase):
    def test_exact_user_regression_typo_repairs_only_for_routing(self):
        result = repair_search_query("Покажи ьізнес ідеї 2026")
        self.assertTrue(result["changed"])
        self.assertEqual(result["original_query"], "Покажи ьізнес ідеї 2026")
        self.assertEqual(result["routing_query"], "Покажи бізнес ідеї 2026")
        self.assertEqual(result["repairs"], [{"from": "ьізнес", "to": "бізнес", "distance": 1}])
        self.assertTrue(result["original_preserved"])
        self.assertTrue(looks_like_business_idea_query("Покажи ьізнес ідеї 2026"))

    def test_arbitrary_names_are_not_spellchecked(self):
        result = repair_search_query("Show Nvidio Zynqora 2026")
        self.assertFalse(result["changed"])
        self.assertEqual(result["routing_query"], "Show Nvidio Zynqora 2026")

    def test_business_idea_intent_is_narrow(self):
        self.assertTrue(looks_like_business_idea_query("business ideas 2026"))
        self.assertTrue(looks_like_business_idea_query("pomysły na biznes 2026"))
        self.assertFalse(looks_like_business_idea_query("Who is the CEO of this business?"))
        self.assertFalse(looks_like_business_idea_query("What is investment banking?"))


class GeneralRelevanceGuardTests(unittest.TestCase):
    def test_zero_overlap_translation_noise_is_rejected(self):
        payload = {
            "intelligence_version": "general-web-v1",
            "intelligence_route": "general_web",
            "results": [
                {
                    "title": "DeepL Translator | El traductor más preciso del mundo",
                    "description": "Traducciones precisas de calidad empresarial.",
                    "url": "https://www.deepl.com/es/translator",
                },
                {
                    "title": "Business ideas 2026",
                    "description": "Business ideas and market opportunities for entrepreneurs.",
                    "url": "https://example.org/business-ideas-2026",
                },
            ],
        }
        result = apply_general_relevance_guard(payload, query="business ideas 2026")
        self.assertEqual([row["title"] for row in result["results"]], ["Business ideas 2026"])
        self.assertEqual(result["relevance_guard"]["zero_overlap_rejected"], 1)
        self.assertTrue(result["relevance_guard"]["provider_rank_is_not_relevance"])

    def test_normal_generic_research_keeps_semantically_matching_page(self):
        payload = {
            "intelligence_version": "general-web-v1",
            "intelligence_route": "general_web",
            "results": [{
                "title": "Photosynthesis overview",
                "description": "Reference guide to plant energy conversion.",
                "url": "https://example.org/photosynthesis",
            }],
        }
        result = apply_general_relevance_guard(payload, query="Explain photosynthesis")
        self.assertEqual(len(result["results"]), 1)


class BusinessIdeaSearchTests(unittest.TestCase):
    def test_regression_query_preserves_original_repairs_typo_and_rejects_translators(self):
        calls = []

        def fake_post(_url, **kwargs):
            search_query = kwargs["json"]["query"]
            calls.append(search_query)
            if search_query == "Покажи ьізнес ідеї 2026":
                rows = [
                    {
                        "title": "DeepL Translator | El traductor más preciso del mundo",
                        "description": "Traductor profesional para múltiples idiomas.",
                        "url": "https://www.deepl.com/es/translator",
                    },
                    {
                        "title": "Google Traductor",
                        "description": "Traduce palabras y páginas web gratis.",
                        "url": "https://translate.google.es/",
                    },
                ]
            elif search_query == "Покажи бізнес ідеї 2026":
                rows = [{
                    "title": "Бізнес ідеї 2026: нові ніші",
                    "description": "Бізнес ідеї для підприємців та аналіз попиту у 2026 році.",
                    "url": "https://example.org/ua/business-ideas-2026",
                }]
            else:
                rows = [
                    {
                        "title": "20 business ideas for 2026",
                        "description": "Business ideas based on market demand and unmet needs in Europe.",
                        "url": "https://example.com/business-ideas-2026",
                    },
                    {
                        "title": "Google Translate",
                        "description": "Translate words between many languages.",
                        "url": "https://translate.google.com/",
                    },
                ]
            return FakeResponse(200, {"provider_status": "complete", "results": rows})

        env = {
            "BRAVE_SEARCH_API_KEY": "",
            "BROWSER_EYE_URL": "http://browser-eye.internal",
            "GLOBAL_SEARCH_BROWSER_TOKEN": "test-browser-token",
        }
        with patch.dict(os.environ, env, clear=False):
            result = search_business_ideas(
                "Покажи ьізнес ідеї 2026",
                country="EU",
                poster=fake_post,
            )

        self.assertEqual(result["intelligence_version"], "business-ideas-v1")
        self.assertEqual(result["intelligence_route"], "business_ideas")
        self.assertEqual(result["route_reason"], "typo_tolerant_business_idea_intent")
        self.assertEqual(result["search_plan"][0], "Покажи ьізнес ідеї 2026")
        self.assertEqual(result["search_plan"][1], "Покажи бізнес ідеї 2026")
        self.assertIn("business ideas 2026 Europe", result["search_plan"][2])
        self.assertEqual(calls, result["search_plan"])
        titles = [row["title"] for row in result["results"]]
        self.assertIn("Бізнес ідеї 2026: нові ніші", titles)
        self.assertIn("20 business ideas for 2026", titles)
        self.assertFalse(any("Traductor" in title or "Translate" in title or "DeepL" in title for title in titles))
        self.assertGreaterEqual(result["relevance_guard"]["zero_or_weak_overlap_rejected"], 3)
        self.assertEqual(result["query_repair"]["original_query"], "Покажи ьізнес ідеї 2026")
        self.assertEqual(result["query_repair"]["routing_query"], "Покажи бізнес ідеї 2026")
        for row in result["results"]:
            self.assertGreaterEqual(row["query_relevance"]["hits"], 2)
            self.assertIn("about", row["ui_explanation"])
            self.assertIn("why", row["ui_explanation"])
            self.assertIn("value", row["ui_explanation"])
            self.assertIn("uncertainty", row["ui_explanation"])

    def test_country_shapes_only_specialized_expansion(self):
        env = {
            "BRAVE_SEARCH_API_KEY": "",
            "BROWSER_EYE_URL": "http://browser-eye.internal",
            "GLOBAL_SEARCH_BROWSER_TOKEN": "test-browser-token",
        }
        calls = []

        def fake_post(_url, **kwargs):
            calls.append(kwargs["json"]["query"])
            return FakeResponse(200, {"provider_status": "complete", "results": []})

        with patch.dict(os.environ, env, clear=False):
            result = search_business_ideas("business ideas 2026", country="PL", poster=fake_post)
        self.assertEqual(result["search_plan"][0], "business ideas 2026")
        self.assertIn("Poland", result["search_plan"][-1])


class PrivateBootstrapRoutingTests(unittest.TestCase):
    def test_private_router_intercepts_typo_business_ideas_without_forcing_money(self):
        import private_global_bootstrap as bootstrap

        expected = {
            "query": "Покажи ьізнес ідеї 2026",
            "intelligence_version": "business-ideas-v1",
            "intelligence_route": "business_ideas",
            "results": [],
        }
        with patch.object(bootstrap, "search_business_ideas", return_value=expected) as idea_search, \
             patch.object(bootstrap, "search_universal", side_effect=AssertionError("generic router must not run")):
            result = bootstrap.search_private_universal(
                "Покажи ьізнес ідеї 2026", category="all", country="EU"
            )
        self.assertEqual(result, expected)
        idea_search.assert_called_once()
        self.assertEqual(idea_search.call_args.kwargs["country"], "EU")

    def test_explicit_money_category_still_uses_existing_universal_router(self):
        import private_global_bootstrap as bootstrap

        payload = {
            "query": "business ideas",
            "intelligence_version": "money-test",
            "intelligence_route": "opportunity",
            "results": [],
        }
        with patch.object(bootstrap, "search_business_ideas", side_effect=AssertionError("must not override explicit Money category")), \
             patch.object(bootstrap, "search_universal", return_value=payload) as universal:
            result = bootstrap.search_private_universal(
                "business ideas", category="grant", country="EU"
            )
        self.assertEqual(result["intelligence_route"], "opportunity")
        universal.assert_called_once()


if __name__ == "__main__":
    unittest.main()
