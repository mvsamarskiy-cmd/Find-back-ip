import os
import unittest
from datetime import date
from unittest.mock import patch

from money_intelligence import normalize_money_payload, normalize_money_row
from money_opportunity_search import money_opportunity_search_capabilities, search_money_opportunities
from money_query_planner import MAX_MONEY_QUERY_LANES, build_money_search_plan, compile_money_profile
from money_sources import source_for_host
from money_taxonomy import TYPE_IDS, infer_money_types, looks_like_material_opportunity
from opportunity_search import infer_query_category


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"{}"
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._payload


class MoneyTaxonomyTests(unittest.TestCase):
    def test_taxonomy_is_broad_and_contains_non_grant_mechanisms(self):
        self.assertGreaterEqual(len(TYPE_IDS), 40)
        for expected in (
            "grant", "preferential_loan", "procurement", "public_auction",
            "classified_offer", "wholesale_closeout", "off_market_public",
        ):
            self.assertIn(expected, TYPE_IDS)

    def test_actionable_asset_search_is_material_opportunity(self):
        query = "Знайди ліквідаційне обладнання для виробництва у Польщі"
        self.assertTrue(looks_like_material_opportunity(query))
        self.assertIn("liquidation", infer_money_types(query))
        self.assertEqual(infer_query_category(query), "material")

    def test_broad_where_is_money_query_routes_material(self):
        self.assertEqual(infer_query_category("Знайди всі матеріальні можливості де є гроші"), "material")

    def test_educational_investment_query_is_not_material_opportunity(self):
        self.assertFalse(looks_like_material_opportunity("What is investment banking?"))
        self.assertEqual(infer_query_category("What is investment banking?"), "funding")
        # Universal router retains the pre-existing ambiguity guard for bare
        # funding/investment terminology; this function only preserves legacy category inference.


class MoneyPlannerTests(unittest.TestCase):
    def test_equipment_need_expands_across_mechanisms(self):
        query = "Потрібно 300 000 PLN на обладнання для виробництва в Польщі"
        plan = build_money_search_plan(query, country="PL")
        self.assertEqual(plan["queries"][0], query)
        self.assertEqual(plan["queries"].count(query), 1)
        self.assertLessEqual(len(plan["queries"]), MAX_MONEY_QUERY_LANES)
        families = {lane.get("family") for lane in plan["lanes"]}
        self.assertTrue({"funding", "finance", "assets", "revenue"} & families)
        profile = plan["profile"]
        self.assertEqual(profile["requested_amount"]["currency"], "PLN")
        self.assertEqual(profile["requested_amount"]["max"], 300000)

    def test_profile_keeps_natural_language_need_without_fake_eligibility(self):
        profile = compile_money_profile("Хочу знайти фінансування обладнання для компанії", country="PL")
        self.assertIn("company", profile["applicant_types"])
        self.assertTrue(profile["requested_families"])


class MoneySourceTests(unittest.TestCase):
    def test_official_and_market_sources_stay_distinct(self):
        self.assertEqual(source_for_host("https://parp.gov.pl/x")["tier"], "official")
        self.assertEqual(source_for_host("https://www.olx.pl/x")["tier"], "market")


class MoneyIntelligenceTests(unittest.TestCase):
    def test_liquidation_record_is_not_called_verified_or_profitable(self):
        profile = compile_money_profile("Знайди ліквідаційне обладнання", country="PL")
        record = normalize_money_row({
            "title": "Wyprzedaż likwidacyjna maszyn produkcyjnych",
            "description": "Cena 50 000 PLN. Oferta sprzedaży maszyn.",
            "url": "https://olx.pl/oferta/123",
            "retrieval_score": 70,
        }, profile=profile)
        self.assertEqual(record["opportunity_type"], "liquidation")
        self.assertEqual(record["family"], "assets")
        self.assertFalse(record["current_call_verified"])
        self.assertFalse(record["practical_ranking"]["guaranteed_return"])
        self.assertEqual(record["amount"]["currency"], "PLN")

    def test_cross_source_duplicate_titles_are_deconflicted(self):
        profile = compile_money_profile("Знайди грант для стартапу", country="PL")
        payload = normalize_money_payload({"results": [
            {"title": "Startup Growth Grant 2026", "description": "Grant up to 100 000 EUR", "url": "https://example.org/a"},
            {"title": "Startup Growth Grant 2026", "description": "Grant up to 100 000 EUR", "url": "https://mirror.example.net/b"},
        ]}, profile=profile)
        self.assertEqual(len(payload["money_records"]), 1)
        self.assertEqual(payload["money_records"][0]["duplicate_evidence_count"], 2)
        self.assertEqual(len(payload["money_records"][0]["source_urls"]), 2)

    def test_closed_status_is_a_blocker(self):
        profile = compile_money_profile("Find grant for startup", country="EU")
        row = normalize_money_row({
            "title": "Startup grant",
            "description": "Applications closed. Deadline 1 January 2025. Grant 100 000 EUR.",
            "url": "https://example.org/closed",
        }, profile=profile)
        self.assertEqual(row["status"], "closed")
        self.assertIn("closed", row["blockers"])
        self.assertFalse(row["likely_eligible"])


class MoneySearchExecutionTests(unittest.TestCase):
    def test_exact_query_is_first_standard_lane_and_search_is_bounded(self):
        calls = []

        def fake_post(url, **kwargs):
            query = kwargs.get("json", {}).get("query")
            calls.append((url, query))
            index = len(calls)
            if url.endswith("/v1/web-search"):
                return FakeResponse(200, {
                    "provider_status": "complete",
                    "results": [{
                        "title": f"Procurement opportunity {index}",
                        "description": "Tender contract 120 000 PLN open call",
                        "url": f"https://example{index}.org/tender",
                    }],
                })
            raise AssertionError("Tor should be disabled in this test")

        def fake_get(*_args, **_kwargs):
            return FakeResponse(404)

        env = {
            "BRAVE_SEARCH_API_KEY": "",
            "BROWSER_EYE_URL": "http://browser-eye.internal",
            "GLOBAL_SEARCH_BROWSER_TOKEN": "token",
            "TOR_OPPORTUNITY_SEARCH_ENABLED": "0",
        }
        query = "Знайди контракти і тендери для виробничої компанії у Польщі"
        with patch.dict(os.environ, env, clear=False):
            payload = search_money_opportunities(query, country="PL", poster=fake_post, requester=fake_get)

        standard_queries = [item[1] for item in calls if item[0].endswith("/v1/web-search")]
        self.assertEqual(standard_queries[0], query)
        self.assertEqual(standard_queries.count(query), 1)
        self.assertLessEqual(len(standard_queries), MAX_MONEY_QUERY_LANES)
        self.assertTrue(payload["money_records"])
        self.assertEqual(payload["money_query_plan"]["queries"][0], query)
        self.assertEqual(payload["money_intelligence_version"], "money-intelligence-v2")

    def test_capabilities_expose_off_market_and_no_automation(self):
        caps = money_opportunity_search_capabilities()
        self.assertEqual(caps["off_market_scope"], "publicly_discoverable_only")
        self.assertFalse(caps["automated_purchase_or_contact"])
        self.assertGreaterEqual(caps["taxonomy"]["type_count"], 40)


if __name__ == "__main__":
    unittest.main()
