import os
import unittest
from unittest.mock import patch

from telegram_bootstrap import RELEASE_MARKER, app


class ProductionVersionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_home_disables_stale_browser_cache(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))
        self.assertEqual(response.headers.get("Pragma"), "no-cache")
        self.assertEqual(response.headers.get("Expires"), "0")

    def test_version_endpoint_reports_release_and_railway_commit(self):
        with patch.dict(os.environ, {"RAILWAY_GIT_COMMIT_SHA": "abc123"}, clear=False):
            response = self.client.get("/api/version")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "release": RELEASE_MARKER,
            "git_commit": "abc123",
        })

    def test_version_endpoint_does_not_require_railway_environment(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get("/api/version")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["git_commit"], "unknown")


if __name__ == "__main__":
    unittest.main()
