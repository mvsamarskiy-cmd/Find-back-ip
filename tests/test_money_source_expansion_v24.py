import threading
import time
import unittest
from unittest.mock import patch

from money_eligibility_apply import apply_eligibility_to_payload
from money_intelligence import normalize_money_payload
from money_query_planner import compile_money_profile
from money_source_expansion import (
    MAX_SOURCE_EXPANSION_LANES,
    build_source_expansion_lanes,
    expanded_source_for_host,
    source_expansion_capabilities,
)
from money_source_expansion_search import (
    MAX_SOURCE_EXPANSION_CONCURRENCY,
    _run_source_lanes,
    search_money_opportunities,
)
from money_verification import verify_money_source


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"{}"

    def json(self):
        return self._payload


class SourceExpansionPlannerTests(unittest.TestCase):
    def test_broad_money_profile_gets_bounded_diverse_source_classes(self):
        profile = compile_money_profile(
            "Знайди всі матеріальні можливості де є гроші, активи, контракти і пропозиції",
            country="PL",
        )
        lanes = build_source_expansion_lanes(profile)
        self.assertGreaterEqual(len(lanes), 3)
        self.assertLessEqual(len(lanes), MAX_SOURCE_EXPANSION_LANES)
        self.assertEqual(len({lane["source_class"] for lane in lanes}), len(lanes))
        self.assertTrue(all(profile["query"] in lane["query"] for lane in lanes))
        self.assertTrue(all(lane["lane"] == "source_class_expansion" for lane in lanes))

    def test_asset_search_prioritizes_public_and_distressed_asset_surfaces(self):
        profile = compile_money_profile("Знайди ліквідаційне обладнання і активи на продаж", country="PL")
        lanes = build_source_expansion_lanes(profile)
        classes = [lane["source_class"] for lane in lanes]
        self.assertIn("public_bulletin", classes)
        self.assertIn("insolvency_assets", classes)

    def test_expanded_registry_recognizes_current_high_value_sources(self):
        arp = expanded_source_for_host("https://www.arp.pl/finansowanie")
        paih = expanded_source_for_host("paih.gov.pl")
        een = expanded_source_for_host("https://een.ec.europa.eu/partnering-opportunities")
        self.assertEqual(arp["source_class"], "public_finance")
        self.assertEqual(arp["tier"], "public")
        self.assertEqual(paih["tier"], "official")
        self.assertEqual(een["source_class"], "eu_partnering")
        caps = source_expansion_capabilities()
        self.assertGreaterEqual(caps["expanded_registry_count"], 6)
        self.assertGreaterEqual(caps["source_class_count"], 10)
        self.assertFalse(caps["officiality_means_listing_verified"])

    def test_source_lanes_use_bounded_concurrency(self):
        lanes = [{"query": f"q{i}", "source_class": f"c{i}"} for i in range(5)]
        lock = threading.Lock()
        active = 0
        maximum = 0

        def fake_run(query, **kwargs):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return "complete", [{"title": query, "description": "", "url": f"https://example.org/{query}"}]

        with patch("money_source_expansion_search._run_standard", side_effect=fake_run):
            outcomes = _run_source_lanes(
                lanes, provider="browser_eye_web", providers={}, requester=None, poster=None,
            )
        self.assertEqual(len(outcomes), 5)
        self.assertGreaterEqual(maximum, 2)
        self.assertLessEqual(maximum, MAX_SOURCE_EXPANSION_CONCURRENCY)


class SourceExpansionSearchTests(unittest.TestCase):
    def _profile(self, query="Знайди supplier contract для SME", country="PL"):
        return compile_money_profile(query, country=country)

    def _base_payload(self, profile, *, title="Base opportunity", url="https://example.org/base", category="supplier_demand"):
        raw = {
            "results": [{
                "title": title,
                "description": "Looking for supplier. Contract value 100000 PLN.",
                "url": url,
                "host": url.split('/')[2],
                "category": category,
                "retrieval_score": 70,
                "source_tier": "web",
                "source_name": "Example",
                "source_country": "PL",
                "official_source": False,
                "transport": "web",
                "query_index": 0,
                "query_lane": "exact",
            }],
            "money_query_plan": {"profile": profile},
            "money_profile": profile,
            "provider": "browser_eye_web",
            "provider_status": "complete",
        }
        normalized = normalize_money_payload(raw, profile=profile)
        normalized = apply_eligibility_to_payload(
            normalized, eligibility_profile=profile.get("eligibility_profile") or {"facts": {}},
        )
        return normalized

    def test_expansion_adds_new_candidate_and_rebuilds_graph(self):
        profile = self._profile()
        base = self._base_payload(profile)
        lane = {
            "lane": "source_class_expansion", "source_class": "export_trade", "query": "site:paih.gov.pl supplier",
            "trust": "official_agency", "families": ["revenue"], "country": "PL",
        }
        raw_expanded = [{
            "title": "PAIH supplier partner opportunity",
            "description": "Looking for supplier and business partner in Poland.",
            "url": "https://paih.gov.pl/opportunity/supplier-a",
        }]
        with patch("money_source_expansion_search.base_money_search", return_value=base), \
             patch("money_source_expansion_search.build_source_expansion_lanes", return_value=[lane]), \
             patch("money_source_expansion_search._provider_choice", return_value=("browser_eye_web", {"browser_eye": False})), \
             patch("money_source_expansion_search._run_source_lanes", return_value=[("complete", raw_expanded)]):
            result = search_money_opportunities(profile["query"], country="PL")
        self.assertEqual(result["source_expansion"]["unique_added_count"], 1)
        self.assertEqual(result["source_expansion"]["raw_candidate_count"], 1)
        self.assertEqual(len(result["money_records"]), 2)
        expanded = next(record for record in result["money_records"] if any("paih.gov.pl" in u for u in record["source_urls"]))
        self.assertTrue(expanded["source_expansion_evidence"])
        self.assertIn("export_trade", expanded["source_classes"])
        graph_urls = {node.get("url") for node in result["opportunity_graph"]["nodes"] if node.get("type") == "source_observation"}
        self.assertIn("https://paih.gov.pl/opportunity/supplier-a", graph_urls)

    def test_duplicate_candidate_preserves_both_original_urls(self):
        profile = self._profile(query="Знайди grant для SME")
        base = self._base_payload(profile, title="Green Growth Grant", url="https://example.org/green", category="grant")
        lane = {
            "lane": "source_class_expansion", "source_class": "eu_sme_agency", "query": "site:eismea.ec.europa.eu Green Growth Grant",
            "trust": "official_database", "families": ["funding"], "country": "EU",
        }
        raw_expanded = [{
            "title": "Green Growth Grant",
            "description": "Open call for SMEs. Grant funding.",
            "url": "https://eismea.ec.europa.eu/green-growth-grant",
        }]
        with patch("money_source_expansion_search.base_money_search", return_value=base), \
             patch("money_source_expansion_search.build_source_expansion_lanes", return_value=[lane]), \
             patch("money_source_expansion_search._provider_choice", return_value=("browser_eye_web", {"browser_eye": False})), \
             patch("money_source_expansion_search._run_source_lanes", return_value=[("complete", raw_expanded)]):
            result = search_money_opportunities(profile["query"], country="PL")
        self.assertEqual(result["source_expansion"]["unique_added_count"], 0)
        self.assertEqual(len(result["money_records"]), 1)
        urls = result["money_records"][0]["source_urls"]
        self.assertIn("https://example.org/green", urls)
        self.assertIn("https://eismea.ec.europa.eu/green-growth-grant", urls)
        self.assertGreaterEqual(result["money_records"][0]["duplicate_evidence_count"], 2)

    def test_no_expansion_results_preserves_base_without_fabrication(self):
        profile = self._profile()
        base = self._base_payload(profile)
        lane = {"lane": "source_class_expansion", "source_class": "supplier_rfq", "query": "q", "trust": "commercial_demand_discovery", "families": ["revenue"], "country": "PL"}
        with patch("money_source_expansion_search.base_money_search", return_value=base), \
             patch("money_source_expansion_search.build_source_expansion_lanes", return_value=[lane]), \
             patch("money_source_expansion_search._provider_choice", return_value=("browser_eye_web", {"browser_eye": False})), \
             patch("money_source_expansion_search._run_source_lanes", return_value=[("complete", [])]):
            result = search_money_opportunities(profile["query"], country="PL")
        self.assertEqual(result["source_expansion"]["raw_candidate_count"], 0)
        self.assertEqual(result["source_expansion"]["unique_added_count"], 0)
        self.assertEqual(len(result["money_records"]), 1)


class ExpandedVerificationTests(unittest.TestCase):
    def test_expanded_official_program_requires_direct_active_evidence(self):
        url = "https://eismea.ec.europa.eu/funding/call-a"
        row = {"url": url, "category": "grant", "official_source": True, "retrieval_score": 90}

        def fetcher(_):
            return {
                "provider_status": "complete", "http_status": 200,
                "requested_url": url, "final_url": url,
                "body_text": "Applications open. Open call. Deadline 31 December 2026. Grant for SMEs.",
                "observed_at": "2026-08-21T18:00:00+00:00", "snapshot_sha256": "a" * 64,
                "public_contacts": {},
            }

        result = verify_money_source(row, evidence_fetcher=fetcher)
        self.assertTrue(result["source_observed"])
        self.assertTrue(result["current_call_verified"])
        self.assertEqual(result["known_source"]["tier"], "official")
        self.assertEqual(result["known_source"]["source_class"], "eu_sme_agency")

    def test_expanded_official_domain_without_active_page_evidence_is_not_current_call_verified(self):
        url = "https://eismea.ec.europa.eu/funding/archive"
        row = {"url": url, "category": "grant", "official_source": True, "retrieval_score": 90}
        result = verify_money_source(row, evidence_fetcher=lambda _: {
            "provider_status": "complete", "http_status": 200,
            "requested_url": url, "final_url": url,
            "body_text": "Funding information and programme overview.",
            "observed_at": "2026-08-21T18:00:00+00:00", "snapshot_sha256": "b" * 64,
            "public_contacts": {},
        })
        self.assertTrue(result["source_observed"])
        self.assertFalse(result["current_call_verified"])


if __name__ == "__main__":
    unittest.main()
