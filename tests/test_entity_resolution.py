import unittest

from entity_resolution import (
    compare_descriptors,
    entity_resolution_capabilities,
    extract_product_descriptor,
    resolve_product_entities,
)
from universal_search_entity import apply_entity_resolution, universal_search_capabilities


def source(title, url, host="shop.example", excerpt=""):
    return {
        "title": title,
        "url": url,
        "host": host,
        "excerpt": excerpt,
        "routes": ["product"],
    }


class ProductDescriptorTests(unittest.TestCase):
    def test_extracts_storage_colour_condition_and_identifier(self):
        descriptor = extract_product_descriptor(source(
            "Apple iPhone 17 Pro 256GB Black SKU: IP17P-256-BLK",
            "https://a.example/item",
            excerpt="Brand new, in stock",
        ))
        self.assertEqual(descriptor["variant"]["storage"], ["256GB"])
        self.assertEqual(descriptor["variant"]["colour"], ["black"])
        self.assertEqual(descriptor["variant"]["condition"], "new")
        self.assertEqual(descriptor["identifiers"]["sku"], "IP17P-256-BLK")

    def test_same_model_same_variant_is_comparison_safe(self):
        left = extract_product_descriptor(source(
            "Apple iPhone 17 Pro 256GB Black 4999 PLN",
            "https://a.example/item",
        ))
        right = extract_product_descriptor(source(
            "iPhone 17 Pro 256 GB Black - 5099 zł | Apple",
            "https://b.example/item",
        ))
        comparison = compare_descriptors(left, right)
        self.assertTrue(comparison["family_match"])
        self.assertTrue(comparison["exact_variant_match"])
        self.assertTrue(comparison["exact_variant_safe"])

    def test_storage_difference_keeps_family_but_splits_variant(self):
        left = extract_product_descriptor(source(
            "Apple iPhone 17 Pro 256GB Black",
            "https://a.example/item",
        ))
        right = extract_product_descriptor(source(
            "Apple iPhone 17 Pro 512GB Black",
            "https://b.example/item",
        ))
        comparison = compare_descriptors(left, right)
        self.assertTrue(comparison["family_match"])
        self.assertIn("storage", comparison["variant_conflicts"])
        self.assertFalse(comparison["exact_variant_match"])

    def test_pro_and_pro_max_are_not_same_family(self):
        left = extract_product_descriptor(source(
            "Apple iPhone 17 Pro 256GB Black",
            "https://a.example/item",
        ))
        right = extract_product_descriptor(source(
            "Apple iPhone 17 Pro Max 256GB Black",
            "https://b.example/item",
        ))
        comparison = compare_descriptors(left, right)
        self.assertTrue(comparison["modifier_conflict"])
        self.assertFalse(comparison["family_match"])

    def test_matching_explicit_sku_overrides_title_variation(self):
        left = extract_product_descriptor(source(
            "Apple smartphone SKU: SAME-1234 256GB Black",
            "https://a.example/item",
        ))
        right = extract_product_descriptor(source(
            "iPhone listing SKU SAME-1234 256 GB Black",
            "https://b.example/item",
        ))
        comparison = compare_descriptors(left, right)
        self.assertTrue(comparison["family_match"])
        self.assertEqual(comparison["basis"], "explicit_identifier_match")
        self.assertEqual(comparison["family_confidence"], 100)


class EntityClusteringTests(unittest.TestCase):
    def test_same_exact_variant_across_two_hosts_creates_safe_comparison_group(self):
        payload = resolve_product_entities([
            source("Apple iPhone 17 Pro 256GB Black 4999 PLN", "https://a.example/iphone", "a.example"),
            source("iPhone 17 Pro 256 GB Black 5099 zł Apple", "https://b.example/iphone", "b.example"),
        ])
        self.assertEqual(payload["family_count"], 1)
        self.assertEqual(payload["entity_count"], 1)
        self.assertEqual(payload["comparison_safe_group_count"], 1)
        entity = payload["entities"][0]
        self.assertTrue(entity["comparison_safe"])
        self.assertEqual(entity["variant"]["storage"], ["256GB"])
        self.assertEqual(entity["variant"]["colour"], ["black"])

    def test_different_storage_creates_two_entities_inside_one_family(self):
        payload = resolve_product_entities([
            source("Apple iPhone 17 Pro 256GB Black", "https://a.example/iphone", "a.example"),
            source("Apple iPhone 17 Pro 512GB Black", "https://b.example/iphone", "b.example"),
        ])
        self.assertEqual(payload["family_count"], 1)
        self.assertEqual(payload["entity_count"], 2)
        self.assertEqual(payload["comparison_safe_group_count"], 0)

    def test_missing_variant_attribute_does_not_become_safe_comparison(self):
        payload = resolve_product_entities([
            source("Apple iPhone 17 Pro 256GB Black", "https://a.example/iphone", "a.example"),
            source("Apple iPhone 17 Pro 256GB", "https://b.example/iphone", "b.example"),
        ])
        self.assertEqual(payload["family_count"], 1)
        self.assertEqual(payload["entity_count"], 1)
        self.assertFalse(payload["entities"][0]["comparison_safe"])

    def test_generic_product_without_distinctive_identity_stays_unresolved(self):
        payload = resolve_product_entities([
            source("Wireless headphones best price", "https://a.example/item", "a.example"),
        ])
        self.assertEqual(payload["family_count"], 0)
        self.assertEqual(len(payload["unresolved_sources"]), 1)


class EntitySynthesisIntegrationTests(unittest.TestCase):
    def test_safe_entity_builds_price_comparison_without_claiming_verification(self):
        payload = {
            "query": "iPhone 17 Pro 256GB Black price",
            "intelligence_route": "product",
            "intelligence_routes": ["product"],
            "synthesis": {
                "top_evidence": [
                    source("Apple iPhone 17 Pro 256GB Black", "https://a.example/iphone", "a.example"),
                    source("iPhone 17 Pro 256 GB Black Apple", "https://b.example/iphone", "b.example"),
                ],
                "observations": [
                    {"type": "price_mention", "currency": "PLN", "value": 4999.0, "source_url": "https://a.example/iphone", "source_host": "a.example", "retrieved_at": "2026-08-21T15:00:00Z", "independently_verified": False},
                    {"type": "price_mention", "currency": "PLN", "value": 5099.0, "source_url": "https://b.example/iphone", "source_host": "b.example", "retrieved_at": "2026-08-21T15:00:00Z", "independently_verified": False},
                ],
                "truth_status": {},
            },
        }
        result = apply_entity_resolution(payload)
        synthesis = result["synthesis"]
        self.assertEqual(synthesis["entity_resolution"]["comparison_safe_group_count"], 1)
        self.assertEqual(len(synthesis["entity_price_comparisons"]), 1)
        comparison = synthesis["entity_price_comparisons"][0]
        self.assertEqual(comparison["min_observed"], 4999.0)
        self.assertEqual(comparison["max_observed"], 5099.0)
        self.assertEqual(comparison["spread"], 100.0)
        self.assertFalse(comparison["verified_price_comparison"])

    def test_different_variants_do_not_create_price_comparison(self):
        payload = {
            "query": "iPhone 17 Pro price",
            "intelligence_route": "product",
            "intelligence_routes": ["product"],
            "synthesis": {
                "top_evidence": [
                    source("Apple iPhone 17 Pro 256GB Black", "https://a.example/iphone", "a.example"),
                    source("Apple iPhone 17 Pro 512GB Black", "https://b.example/iphone", "b.example"),
                ],
                "observations": [
                    {"type": "price_mention", "currency": "PLN", "value": 4999.0, "source_url": "https://a.example/iphone", "source_host": "a.example"},
                    {"type": "price_mention", "currency": "PLN", "value": 5999.0, "source_url": "https://b.example/iphone", "source_host": "b.example"},
                ],
                "truth_status": {},
            },
        }
        result = apply_entity_resolution(payload)
        self.assertEqual(result["synthesis"]["entity_price_comparisons"], [])

    def test_non_product_route_is_noop_resolution(self):
        payload = {
            "query": "latest Nvidia news",
            "intelligence_route": "news",
            "intelligence_routes": ["news"],
            "synthesis": {"top_evidence": [], "observations": [], "truth_status": {}},
        }
        result = apply_entity_resolution(payload)
        resolution = result["synthesis"]["entity_resolution"]
        self.assertEqual(resolution["mode"], "not_applicable")
        self.assertEqual(result["synthesis"]["entity_price_comparisons"], [])

    def test_capabilities_advance_router_v5(self):
        caps = universal_search_capabilities()
        self.assertEqual(caps["intelligence_version"], "universal-router-v5")
        self.assertEqual(caps["entity_resolution"]["version"], "entity-resolution-v1")
        self.assertTrue(caps["entity_resolution"]["comparison_requires_exact_variant_evidence"])
        self.assertFalse(caps["entity_resolution"]["external_catalog_lookup"])
        self.assertEqual(entity_resolution_capabilities()["scope"], "product_evidence")


if __name__ == "__main__":
    unittest.main()
