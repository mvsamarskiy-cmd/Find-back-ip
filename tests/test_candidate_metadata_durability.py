import json
from pathlib import Path
import types
import unittest

from session_api import MAX_CANDIDATE_BYTES, _clean_candidate
from telegram_bootstrap import RELEASE_MARKER, app


class CandidateMetadataDurabilityTests(unittest.TestCase):
    def setUp(self):
        self.app_module = types.SimpleNamespace(
            RESOURCE_KEYS={"com", "instagram", "telegram", "tiktok", "youtube", "facebook", "x"}
        )

    def test_generic_and_live_metadata_survive_candidate_sanitizing(self):
        clean = _clean_candidate({
            "name": "Botanell",
            "product_mode": "generic_name",
            "entry_mode": "generic_name",
            "pronunciation": "bo-ta-nell",
            "language_risks": ["none observed"],
            "verification_state": "checking",
            "lifecycle_event_seq": 27,
            "checked": False,
            "availability": {},
            "verification": {},
        }, self.app_module)
        self.assertEqual(clean["product_mode"], "generic_name")
        self.assertEqual(clean["entry_mode"], "generic_name")
        self.assertEqual(clean["pronunciation"], "bo-ta-nell")
        self.assertEqual(clean["language_risks"], ["none observed"])
        self.assertEqual(clean["verification_state"], "checking")
        self.assertEqual(clean["lifecycle_event_seq"], 27)

    def test_brand_collision_is_compacted_but_keeps_client_card_summary(self):
        raw = {
            "name": "Botanell",
            "checked": True,
            "availability": {},
            "verification": {},
            "brand_collision_checked_at": "2026-08-18T20:00:00Z",
            "brand_collision": {
                "candidate": "Botanell",
                "collision_signal": "medium",
                "clearance_complete": False,
                "legal_clearance": False,
                "recommendation": "manual_review_required",
                "notice": "screening only",
                "coverage": {
                    "web_automated": True,
                    "companies_uk_automated": True,
                    "companies_requested_markets": ["PL", "GB", "INTL"],
                    "trademarks_automated": False,
                    "trademark_territories": ["EU", "PL", "INTL"],
                    "nice_classes": [9, 35],
                },
                "web": {
                    "provider": "brave_web",
                    "configured": True,
                    "status": "complete",
                    "signal": "medium",
                    "reason": "observed",
                    "counts": {"observed": 20, "exact_domain": 0},
                    "manual_search": "https://www.google.com/search?q=Botanell",
                    "results": [{"title": "huge raw result", "description": "x" * 5000}] * 10,
                },
                "companies": {
                    "uk": {
                        "provider": "companies_house",
                        "coverage": "United Kingdom",
                        "configured": True,
                        "status": "complete",
                        "signal": "medium",
                        "reason": "observed",
                        "counts": {"observed": 3, "similar_active": 1},
                        "results": [{"name": "x" * 2000}] * 10,
                    },
                    "manual_sources": [{
                        "market": "PL",
                        "label": "KRS",
                        "url": "https://wyszukiwarka-krs.ms.gov.pl/",
                        "automation": "manual_search_required",
                    }],
                },
                "trademarks": {
                    "candidate": "Botanell",
                    "risk": "unknown",
                    "assessment": "manual_search_required",
                    "territories": ["EU", "PL", "INTL"],
                    "nice_classes": [9, 35],
                    "notice": "manual",
                    "sources": {
                        "euipo": {"label": "EUIPO", "url": "https://euipo.europa.eu/", "coverage": "EU"},
                    },
                    "criteria": ["identical_sign", "similar_sign"],
                },
            },
        }
        clean = _clean_candidate(raw, self.app_module)
        collision = clean["brand_collision"]
        self.assertEqual(collision["collision_signal"], "medium")
        self.assertEqual(collision["web"]["counts"]["observed"], 20)
        self.assertEqual(collision["companies"]["uk"]["counts"]["similar_active"], 1)
        self.assertIn("euipo", collision["trademarks"]["sources"])
        self.assertNotIn("results", collision["web"])
        self.assertNotIn("results", collision["companies"]["uk"])
        self.assertLess(len(json.dumps(clean, ensure_ascii=False).encode("utf-8")), MAX_CANDIDATE_BYTES)

    def test_sync_fingerprint_includes_new_metadata_and_cache_is_busted(self):
        source = Path("static/session_sync.js").read_text(encoding="utf-8")
        for key in (
            "product_mode", "entry_mode", "pronunciation", "language_risks",
            "verification_state", "lifecycle_event_seq", "brand_collision",
            "brand_collision_checked_at",
        ):
            self.assertIn(key, source)
        self.assertIn("mergeDurableExtras", source)
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('/static/session_sync.js?v=6', body)
        self.assertEqual(RELEASE_MARKER, "v8.6-variant-api")


if __name__ == "__main__":
    unittest.main()
