import unittest

from verification.benchmark import Fixture, evaluate, summary
from verification.no_key_catalog import no_key_capabilities
from verification.providers import socialscan_adapter


class NoKeyVerifierTests(unittest.TestCase):
    def test_catalog_marks_only_existing_layers_enabled(self):
        catalog = no_key_capabilities()
        self.assertTrue(catalog["direct_public_web"]["enabled"])
        self.assertTrue(catalog["verisign_rdap"]["enabled"])
        self.assertFalse(catalog["socialscan"]["enabled"])
        self.assertFalse(catalog["whatsmyname"]["enabled"])
        self.assertFalse(catalog["maigret"]["enabled"])

    def test_socialscan_unsupported_resource_fails_closed(self):
        row = socialscan_adapter.check_username("example", "telegram")
        self.assertEqual(row["signal"], "unknown")
        self.assertEqual(row["source"], "socialscan")

    def test_benchmark_never_infers_unseen_availability(self):
        fixtures = [Fixture("known", "x", "exists")]

        def checker(handle, platform):
            return {"signal": "unknown", "source": "test", "latency_ms": 1}

        rows = evaluate(fixtures, checker)
        self.assertFalse(rows[0]["matched"])
        self.assertEqual(rows[0]["actual"], "unknown")
        self.assertEqual(summary(rows)["accuracy_on_known_fixtures"], 0.0)

    def test_benchmark_summary_counts_matches(self):
        rows = [
            {"matched": True},
            {"matched": False},
            {"matched": True},
        ]
        stats = summary(rows)
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["matched"], 2)
        self.assertEqual(stats["failed"], 1)


if __name__ == "__main__":
    unittest.main()
