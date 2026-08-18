import unittest

from identity_bundle import classify_identity_bundle, normalize_required_resources


class IdentityBundleTests(unittest.TestCase):
    def test_required_defaults_to_every_selected_resource(self):
        self.assertEqual(
            normalize_required_resources(None, ["telegram", "com"]),
            ("com", "telegram"),
        )

    def test_required_must_be_selected(self):
        with self.assertRaises(ValueError):
            normalize_required_resources(["youtube"], ["telegram"])

    def test_taken_required_resource_is_conflict(self):
        result = classify_identity_bundle({
            "com": {"status": "claimable"},
            "telegram": {"status": "taken"},
        }, ["com", "telegram"])
        self.assertEqual(result["bundle_state"], "conflict")
        self.assertEqual(result["bundle_conflicts"], ["telegram"])

    def test_all_actionable_required_resources_are_confirmed(self):
        result = classify_identity_bundle({
            "com": {"status": "claimable"},
            "telegram": {"status": "purchasable"},
        }, ["com", "telegram"])
        self.assertEqual(result["bundle_state"], "confirmed")
        self.assertEqual(result["bundle_promising"], [])

    def test_not_found_is_promising_not_confirmed(self):
        result = classify_identity_bundle({
            "com": {"status": "claimable"},
            "instagram": {"status": "not_found"},
        }, ["com", "instagram"])
        self.assertEqual(result["bundle_state"], "promising")
        self.assertEqual(result["bundle_promising"], ["instagram"])

    def test_unknown_or_missing_required_resource_is_unresolved(self):
        explicit = classify_identity_bundle({
            "telegram": {"status": "unknown"},
        }, ["telegram"])
        missing = classify_identity_bundle({}, ["telegram"])
        self.assertEqual(explicit["bundle_state"], "unresolved")
        self.assertEqual(missing["bundle_state"], "unresolved")

    def test_conflict_wins_when_another_required_resource_is_unresolved(self):
        result = classify_identity_bundle({
            "com": {"status": "taken"},
            "telegram": {"status": "rate_limited"},
        }, ["com", "telegram"])
        self.assertEqual(result["bundle_state"], "conflict")
        self.assertEqual(result["bundle_conflicts"], ["com"])


if __name__ == "__main__":
    unittest.main()
