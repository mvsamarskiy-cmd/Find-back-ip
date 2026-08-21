import unittest

from universal_search_synthesis import search_universal, universal_search_capabilities


class SynthesisSemanticsTests(unittest.TestCase):
    def test_query_level_monetary_variance_requires_entity_resolution(self):
        def fake_general(query, **_kwargs):
            return {
                "query": query,
                "provider": "fake",
                "provider_status": "complete",
                "results": [],
                "search_plan": [query],
                "intelligence_version": "general-web-v1",
            }

        def fake_synthesizer(_payload):
            return {
                "version": "evidence-synthesis-v1",
                "conflict_candidates": [{
                    "kind": "price_or_amount_variance",
                    "status": "possible_conflict_needs_verification",
                    "observed_values": [1000.0, 2000.0],
                }],
            }

        payload = search_universal(
            "Explain photosynthesis",
            general_searcher=fake_general,
            synthesizer=fake_synthesizer,
        )
        candidate = payload["synthesis"]["conflict_candidates"][0]
        self.assertEqual(candidate["kind"], "monetary_variance_candidate")
        self.assertEqual(candidate["scope"], "query_level")
        self.assertTrue(candidate["entity_resolution_required"])
        self.assertIn("Entity resolution is required", candidate["reason"])

    def test_capabilities_do_not_claim_entity_resolution(self):
        caps = universal_search_capabilities()["answer_synthesis"]
        self.assertFalse(caps["entity_resolution"])
        self.assertEqual(caps["monetary_variance_scope"], "query_level_candidate")


if __name__ == "__main__":
    unittest.main()
