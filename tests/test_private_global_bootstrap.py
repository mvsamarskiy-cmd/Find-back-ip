import unittest

from private_global_bootstrap import app


class PrivateGlobalBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_private_controller_loads_after_public_search_controllers(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("/static/search_actions_v2.js?v=1", body)
        self.assertIn("/static/flow_clarity_v4.js?v=1", body)
        self.assertIn("/static/private_global_mode.js?v=2", body)
        self.assertIn("/static/universal_global_mode.js?v=2", body)
        self.assertLess(body.index("/static/search_actions_v2.js?v=1"), body.index("/static/private_global_mode.js?v=2"))
        self.assertLess(body.index("/static/flow_clarity_v4.js?v=1"), body.index("/static/private_global_mode.js?v=2"))
        self.assertLess(body.index("/static/private_global_mode.js?v=2"), body.index("/static/universal_global_mode.js?v=2"))

    def test_private_diagnostics_expose_state_not_secrets(self):
        payload = self.client.get("/api/private-mode/diagnostics").get_json()
        self.assertIn("configured", payload)
        self.assertTrue(payload["backend_authorized"])
        self.assertFalse(payload["plaintext_secret_in_client"])
        self.assertNotIn("unlock_hash", payload)
        self.assertNotIn("lock_hash", payload)
        self.assertNotIn("session_key", payload)

        universal = payload["universal_search"]
        self.assertEqual(universal["intelligence_version"], "universal-router-v2")
        self.assertEqual(
            set(universal["modules"]),
            {"local", "product", "technical", "news", "company", "person"},
        )
        for module in universal["modules"].values():
            self.assertTrue(module["preferred_host_ranking_only"])
            self.assertEqual(
                module["truth_semantics"],
                "retrieval_evidence_not_verified_fact",
            )


if __name__ == "__main__":
    unittest.main()
