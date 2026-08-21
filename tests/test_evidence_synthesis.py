import unittest
from datetime import datetime, timezone

from evidence_synthesis import (
    evidence_synthesis_capabilities,
    synthesize_search_payload,
)
from universal_search_synthesis import search_universal, universal_search_capabilities


class EvidenceSynthesisTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 21, 15, 10, tzinfo=timezone.utc)

    def test_product_local_evidence_extracts_observations_without_verifying_them(self):
        payload = {
            "query": "laptop in Warsaw where to buy today",
            "provider": "browser_eye_web",
            "provider_status": "complete",
            "intelligence_route": "product",
            "intelligence_routes": ["product", "local"],
            "results": [
                {
                    "title": "Laptop X 3999 zł - in stock",
                    "description": "Open now in Warsaw",
                    "url": "https://shop-a.example/laptop-x",
                    "host": "shop-a.example",
                    "retrieval_score": 91,
                    "intelligence_routes": ["product", "local"],
                    "evidence_lanes": ["shared", "product"],
                    "preferred_source_match": False,
                    "official_source": False,
                },
                {
                    "title": "Laptop X 4199 PLN - out of stock",
                    "description": "Store closed now",
                    "url": "https://shop-b.example/laptop-x",
                    "host": "shop-b.example",
                    "retrieval_score": 88,
                    "intelligence_routes": ["product", "local"],
                    "evidence_lanes": ["local"],
                    "preferred_source_match": False,
                    "official_source": False,
                },
            ],
        }

        synthesis = synthesize_search_payload(payload, now=self.now)

        self.assertEqual(synthesis["version"], "evidence-synthesis-v1")
        self.assertEqual(synthesis["routes"], ["product", "local"])
        self.assertEqual(synthesis["summary"]["unique_host_count"], 2)
        self.assertEqual(synthesis["summary"]["explicitly_verified_source_count"], 0)
        self.assertFalse(synthesis["truth_status"]["verified_fact_generation"])
        self.assertTrue(synthesis["truth_status"]["conflicts_preserved"])

        prices = [item for item in synthesis["observations"] if item["type"] == "price_mention"]
        self.assertEqual({item["value"] for item in prices}, {3999.0, 4199.0})
        self.assertTrue(all(not item["independently_verified"] for item in prices))

        availability = {
            item["value"]
            for item in synthesis["observations"]
            if item["type"] == "availability_mention"
        }
        self.assertEqual(availability, {"available", "unavailable"})

        opening = {
            item["value"]
            for item in synthesis["observations"]
            if item["type"] == "opening_status_mention"
        }
        self.assertEqual(opening, {"open", "closed"})

        conflict_kinds = {item["kind"] for item in synthesis["conflict_candidates"]}
        self.assertIn("price_or_amount_variance", conflict_kinds)
        self.assertIn("availability_status_variance", conflict_kinds)
        self.assertIn("opening_status_variance", conflict_kinds)

    def test_freshness_does_not_invent_publication_date(self):
        payload = {
            "query": "latest product price",
            "intelligence_route": "product",
            "results": [{
                "title": "Product 999 PLN",
                "description": "Observed listing",
                "url": "https://example.org/product",
                "host": "example.org",
            }],
        }
        synthesis = synthesize_search_payload(payload, now=self.now)
        freshness = synthesis["top_evidence"][0]["freshness"]
        self.assertEqual(freshness["basis"], "retrieval_time_only")
        self.assertIsNone(freshness["source_published_at"])
        self.assertEqual(freshness["retrieved_at"], "2026-08-21T15:10:00Z")

    def test_source_date_is_preserved_but_not_promoted_to_verification(self):
        payload = {
            "query": "company news",
            "intelligence_route": "news",
            "results": [{
                "title": "Company update",
                "description": "Observed result",
                "url": "https://news.example/update",
                "host": "news.example",
                "published_at": "2026-08-21T12:00:00Z",
                "official_source": True,
            }],
        }
        synthesis = synthesize_search_payload(payload, now=self.now)
        source = synthesis["top_evidence"][0]
        self.assertEqual(source["freshness"]["basis"], "source_date_plus_retrieval_time")
        self.assertEqual(source["freshness"]["source_published_at"], "2026-08-21T12:00:00Z")
        self.assertTrue(source["verification"]["official_source"])
        self.assertFalse(source["verification"]["independently_verified"])

    def test_explicit_upstream_verification_is_preserved_not_inferred(self):
        payload = {
            "query": "verified opportunity",
            "intelligence_route": "opportunity",
            "results": [{
                "title": "Official call",
                "description": "Official source fetch",
                "url": "https://example.gov/call",
                "host": "example.gov",
                "verification": {"verified": True, "status": "source_fetched"},
            }],
        }
        synthesis = synthesize_search_payload(payload, now=self.now)
        source = synthesis["top_evidence"][0]
        self.assertTrue(source["verification"]["independently_verified"])
        self.assertEqual(synthesis["summary"]["explicitly_verified_source_count"], 1)

    def test_empty_results_return_a_truthful_empty_synthesis(self):
        synthesis = synthesize_search_payload({
            "query": "something",
            "intelligence_route": "general_web",
            "provider_status": "unconfigured",
            "results": [],
        }, now=self.now)
        self.assertEqual(synthesis["summary"]["top_evidence_count"], 0)
        self.assertEqual(synthesis["observations"], [])
        self.assertEqual(synthesis["conflict_candidates"], [])
        self.assertEqual(synthesis["source_coverage"]["provider_status"], "unconfigured")

    def test_capabilities_publish_conservative_synthesis_contract(self):
        caps = evidence_synthesis_capabilities()
        self.assertEqual(caps["version"], "evidence-synthesis-v1")
        self.assertTrue(caps["deterministic"])
        self.assertTrue(caps["conflict_candidates"])
        self.assertEqual(caps["truth_semantics"], "retrieval_evidence_not_verified_fact")


class UniversalSearchSynthesisTests(unittest.TestCase):
    def test_wrapper_preserves_v3_route_and_attaches_synthesis(self):
        calls = []

        def fake_module(query, **kwargs):
            calls.append((query, kwargs["route"]))
            return {
                "query": query,
                "provider": "fake",
                "provider_status": "complete",
                "results": [{
                    "title": "iPhone 17 4999 PLN",
                    "description": "Observed listing",
                    "url": "https://example.org/iphone",
                    "host": "example.org",
                }],
                "search_plan": [query],
                "intelligence_version": "product-v1",
            }

        payload = search_universal(
            "iPhone 17 price in Poland",
            module_searcher=fake_module,
        )

        self.assertEqual(calls, [("iPhone 17 price in Poland", "product")])
        self.assertEqual(payload["intelligence_route"], "product")
        self.assertEqual(payload["intelligence_routes"], ["product"])
        self.assertIn("synthesis", payload)
        self.assertEqual(payload["synthesis"]["version"], "evidence-synthesis-v1")
        self.assertEqual(payload["synthesis"]["observations"][0]["type"], "price_mention")

    def test_capabilities_advance_router_version_and_expose_synthesis(self):
        caps = universal_search_capabilities()
        self.assertEqual(caps["intelligence_version"], "universal-router-v4")
        self.assertEqual(caps["answer_synthesis"]["version"], "evidence-synthesis-v1")
        self.assertTrue(caps["answer_synthesis"]["conflict_candidates"])


if __name__ == "__main__":
    unittest.main()
