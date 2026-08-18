import os
from pathlib import Path
import unittest
from unittest.mock import patch

from brand_collision import (
    brave_web_collision,
    build_brand_collision,
    companies_house_collision,
)
from telegram_bootstrap import app


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = b"{}"

    def json(self):
        return self._payload


class BrandCollisionEngineTests(unittest.TestCase):
    def test_unconfigured_sources_stay_unknown_and_never_brand_free(self):
        with patch.dict(os.environ, {}, clear=True):
            result = build_brand_collision("Botanell")
        self.assertEqual(result["collision_signal"], "unknown")
        self.assertFalse(result["clearance_complete"])
        self.assertFalse(result["legal_clearance"])
        self.assertFalse(result["coverage"]["web_automated"])
        self.assertFalse(result["coverage"]["companies_uk_automated"])
        self.assertFalse(result["coverage"]["trademarks_automated"])
        self.assertNotIn("free", result["notice"].lower())

    def test_brave_exact_domain_is_high_collision_signal(self):
        def requester(url, **kwargs):
            return FakeResponse({
                "web": {
                    "results": [
                        {
                            "title": "Botanell",
                            "url": "https://botanell.com/",
                            "description": "Official Botanell company website",
                        }
                    ]
                }
            })

        with patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "secret"}, clear=True):
            result = brave_web_collision("Botanell", requester=requester)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["signal"], "high")
        self.assertEqual(result["counts"]["exact_domain"], 1)

    def test_companies_house_exact_active_company_is_high(self):
        def requester(url, **kwargs):
            return FakeResponse({
                "items": [
                    {
                        "title": "BOTANELL LIMITED",
                        "company_number": "12345678",
                        "company_status": "active",
                        "address_snippet": "London",
                        "date_of_creation": "2025-01-01",
                    }
                ]
            })

        with patch.dict(os.environ, {"COMPANIES_HOUSE_API_KEY": "secret"}, clear=True):
            result = companies_house_collision("Botanell", requester=requester)
        self.assertEqual(result["signal"], "high")
        self.assertEqual(result["counts"]["exact_active"], 1)
        self.assertTrue(result["results"][0]["exact"])

    def test_no_hits_are_not_promoted_to_legal_clearance(self):
        def requester(url, **kwargs):
            if "api.search.brave.com" in url:
                return FakeResponse({"web": {"results": []}})
            return FakeResponse({"items": []})

        env = {
            "BRAVE_SEARCH_API_KEY": "brave",
            "COMPANIES_HOUSE_API_KEY": "companies",
        }
        with patch.dict(os.environ, env, clear=True):
            result = build_brand_collision("Botanell", requester=requester)
        self.assertEqual(result["collision_signal"], "none_observed")
        self.assertEqual(result["recommendation"], "continue_due_diligence")
        self.assertFalse(result["clearance_complete"])
        self.assertFalse(result["legal_clearance"])
        self.assertEqual(result["trademarks"]["assessment"], "manual_search_required")


class BrandCollisionApiAndUiTests(unittest.TestCase):
    def test_api_is_installed_and_reports_conservative_diagnostics(self):
        client = app.test_client()
        diagnostics = client.get("/api/brand-collision/diagnostics")
        self.assertEqual(diagnostics.status_code, 200)
        payload = diagnostics.get_json()
        self.assertTrue(payload["enabled"])
        self.assertFalse(payload["can_return_brand_free"])
        self.assertEqual(payload["semantic"], "collision_screening_not_brand_availability")

    def test_api_rejects_missing_candidate(self):
        response = app.test_client().post("/api/brand-collision", json={})
        self.assertEqual(response.status_code, 400)

    def test_brand_collision_ui_is_brand_only_and_never_says_globally_free(self):
        source = Path("static/brand_collision_ui.js").read_text(encoding="utf-8")
        self.assertIn("entryMode", source)
        self.assertIn("=== 'brand'", source)
        self.assertIn("Перевірити бренд", source)
        self.assertIn("screening", source)
        self.assertIn("не юридичне підтвердження", source)
        self.assertNotIn("бренд вільний", source.lower())

    def test_bootstrap_loads_collision_ui_after_entry_modes_and_bumps_release(self):
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('/static/entry_modes.js?v=1', body)
        self.assertIn('/static/brand_collision_ui.js?v=1', body)
        self.assertLess(body.index('/static/entry_modes.js?v=1'), body.index('/static/brand_collision_ui.js?v=1'))
        version = app.test_client().get("/api/version").get_json()
        self.assertEqual(version["release"], "v8.3-brand-collision-v1")


if __name__ == "__main__":
    unittest.main()
