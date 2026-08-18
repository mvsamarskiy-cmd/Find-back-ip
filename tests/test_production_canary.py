import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "production_canary", ROOT / "verification" / "production_canary.py"
)
CANARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANARY)


class ProductionCanaryTests(unittest.TestCase):
    def setUp(self):
        self.base = "https://example.test"
        self.payloads = {
            f"{self.base}/health": {"status": "ok"},
            f"{self.base}/api/version": {
                "release": "v8.5.1-candidate-metadata",
                "git_commit": "abc123",
            },
            f"{self.base}/api/verification/diagnostics": {
                "strict_free_semantics": {
                    "green_status": "claimable",
                    "purchasable_is_green": False,
                    "not_found_is_green": False,
                },
                "large_feed_navigation": {
                    "newest_first": True,
                    "pagination": True,
                },
            },
            f"{self.base}/api/background-search": {
                "configured": True,
                "enabled": True,
                "worker_online": True,
                "worker_count": 1,
                "ready": True,
            },
        }

    def fetch(self, url):
        return self.payloads[url]

    def test_canary_checks_release_truth_semantics_and_worker(self):
        report = CANARY.run_canary(
            self.base,
            expected_release="v8.5.1-candidate-metadata",
            require_worker=True,
            fetch_json=self.fetch,
        )
        self.assertEqual(report["health"], "ok")
        self.assertEqual(report["strict_green_status"], "claimable")
        self.assertTrue(report["feed"]["pagination"])
        self.assertTrue(report["background_search"]["ready"])

    def test_canary_rejects_not_found_becoming_green(self):
        self.payloads[f"{self.base}/api/verification/diagnostics"]["strict_free_semantics"][
            "not_found_is_green"
        ] = True
        with self.assertRaisesRegex(CANARY.CanaryError, "not_found"):
            CANARY.run_canary(self.base, fetch_json=self.fetch)

    def test_canary_rejects_release_mismatch(self):
        with self.assertRaisesRegex(CANARY.CanaryError, "Release mismatch"):
            CANARY.run_canary(
                self.base,
                expected_release="v9-does-not-exist",
                fetch_json=self.fetch,
            )

    def test_worker_is_optional_but_enforced_when_requested(self):
        background = self.payloads[f"{self.base}/api/background-search"]
        background.update({"worker_online": False, "worker_count": 0, "ready": False})
        report = CANARY.run_canary(self.base, fetch_json=self.fetch)
        self.assertFalse(report["background_search"]["worker_online"])
        with self.assertRaisesRegex(CANARY.CanaryError, "worker is offline"):
            CANARY.run_canary(
                self.base,
                require_worker=True,
                fetch_json=self.fetch,
            )

    def test_https_is_required(self):
        with self.assertRaisesRegex(CANARY.CanaryError, "HTTPS"):
            CANARY.run_canary("http://example.test", fetch_json=self.fetch)


if __name__ == "__main__":
    unittest.main()
