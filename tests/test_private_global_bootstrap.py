import unittest

from private_global_bootstrap import app


class PrivateGlobalBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_private_controller_loads_after_public_search_controllers(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("/static/search_actions_v2.js?v=1", body)
        self.assertIn("/static/flow_clarity_v4.js?v=1", body)
        self.assertIn("/static/private_global_mode.js?v=3", body)
        self.assertIn("/static/universal_global_mode.js?v=2", body)
        self.assertIn("/static/private_money_controls_v24.js?v=1", body)
        self.assertIn("/static/private_research_browser.js?v=1", body)
        self.assertLess(body.index("/static/search_actions_v2.js?v=1"), body.index("/static/private_global_mode.js?v=3"))
        self.assertLess(body.index("/static/flow_clarity_v4.js?v=1"), body.index("/static/private_global_mode.js?v=3"))
        self.assertLess(body.index("/static/private_global_mode.js?v=3"), body.index("/static/universal_global_mode.js?v=2"))
        self.assertLess(body.index("/static/universal_global_mode.js?v=2"), body.index("/static/private_money_controls_v24.js?v=1"))
        self.assertLess(body.index("/static/private_money_controls_v24.js?v=1"), body.index("/static/private_research_browser.js?v=1"))

    def test_private_diagnostics_expose_state_not_secrets(self):
        payload = self.client.get("/api/private-mode/diagnostics").get_json()
        self.assertIn("configured", payload)
        self.assertTrue(payload["backend_authorized"])
        self.assertFalse(payload["plaintext_secret_in_client"])
        self.assertTrue(payload["cooperative_search_stop"])
        self.assertNotIn("unlock_hash", payload)
        self.assertNotIn("lock_hash", payload)
        self.assertNotIn("session_key", payload)

        universal = payload["universal_search"]
        self.assertEqual(universal["intelligence_version"], "universal-router-v5")
        self.assertTrue(universal["natural_language_multi_intent_planning"])
        self.assertEqual(universal["multi_intent"]["version"], "multi-intent-v1")
        self.assertEqual(universal["multi_intent"]["max_routes"], 3)
        self.assertEqual(universal["answer_synthesis"]["version"], "evidence-synthesis-v1")
        self.assertTrue(universal["answer_synthesis"]["deterministic"])
        self.assertTrue(universal["answer_synthesis"]["conflict_candidates"])
        self.assertEqual(universal["answer_synthesis"]["truth_semantics"], "retrieval_evidence_not_verified_fact")
        entity = universal["entity_resolution"]
        self.assertEqual(entity["version"], "entity-resolution-v1")
        self.assertEqual(entity["scope"], "product_evidence")
        self.assertTrue(entity["family_resolution"])
        self.assertTrue(entity["variant_resolution"])
        self.assertTrue(entity["comparison_requires_exact_variant_evidence"])
        self.assertFalse(entity["external_catalog_lookup"])
        tor = universal["opportunity_transport"]
        self.assertEqual(tor["version"], "tor-opportunity-retrieval-v1")
        self.assertTrue(tor["onion_service_evidence"])
        self.assertTrue(tor["onion_location_discovery"])
        self.assertFalse(tor["verification_inferred_from_tor"])
        self.assertEqual(universal["retrieval_transport_version"], "tor-opportunity-transport-v1")
        self.assertEqual(set(universal["modules"]), {"local", "product", "technical", "news", "company", "person"})
        for module in universal["modules"].values():
            self.assertTrue(module["preferred_host_ranking_only"])
            self.assertEqual(module["truth_semantics"], "retrieval_evidence_not_verified_fact")

        research = payload["research_evidence"]
        self.assertEqual(research["version"], "journalist-evidence-v1")
        self.assertTrue(research["private_session_required"])
        self.assertTrue(research["endpoint_hidden_when_locked"])
        self.assertTrue(research["original_url_preserved"])
        self.assertTrue(research["public_contact_extraction"])
        self.assertFalse(research["login_automation"])
        self.assertFalse(research["form_submission"])
        self.assertFalse(research["purchase_automation"])


if __name__ == "__main__":
    unittest.main()
