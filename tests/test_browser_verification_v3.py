from pathlib import Path
import unittest

from browser_enrichment import (
    apply_browser_enrichment,
    merge_browser_platform,
    persist_browser_enrichment,
)
from browser_eye_service import fingerprint_from_snapshot, search_fingerprint
from durable_candidate_events import DurableCandidateEventStore
from session_store import SessionStore
from telegram_bootstrap import RELEASE_MARKER, app


class BrowserFingerprintTests(unittest.TestCase):
    def test_structured_rendered_identity_confirms_presence(self):
        row = fingerprint_from_snapshot(
            "instagram",
            "dawnflock",
            {
                "title": "Dawn Flock (@dawnflock) • Instagram",
                "canonical": "https://www.instagram.com/dawnflock/",
                "og_title": "Dawn Flock (@dawnflock)",
                "og_image": "https://cdn.example/avatar.jpg",
                "og_description": "Wild birds",
                "body_text": "Dawn Flock",
                "script_text": '{"username":"dawnflock","user_id":"12345678"}',
                "final_url": "https://www.instagram.com/dawnflock/",
            },
            [{"url": "https://www.instagram.com/api/profile", "body": '{"username":"dawnflock"}'}],
            engine="chromium",
            latency_ms=410,
            http_status=200,
        )
        self.assertEqual(row["signal"], "exists")
        self.assertTrue(row["username_exact"])
        self.assertEqual(row["display_name"], "Dawn Flock")
        self.assertTrue(row["avatar_present"])
        self.assertEqual(row["profile_id"], "12345678")
        self.assertTrue(row["network_identity"])
        self.assertEqual(row["claimability"], "unconfirmed")

    def test_explicit_missing_marker_is_absence_not_claimability(self):
        row = fingerprint_from_snapshot(
            "tiktok",
            "dawnflock",
            {
                "title": "TikTok",
                "canonical": "",
                "body_text": "Couldn't find this account",
                "script_text": "",
                "final_url": "https://www.tiktok.com/@dawnflock",
            },
            engine="webkit",
            http_status=200,
        )
        self.assertEqual(row["signal"], "absent")
        self.assertEqual(row["claimability"], "unconfirmed")
        self.assertFalse(row["authoritative_claimability"])

    def test_google_exact_hit_is_collision_corroboration_only(self):
        row = search_fingerprint(
            'site:instagram.com "dawnflock"',
            "dawnflock",
            "instagram",
            {
                "body_text": "results",
                "links": [
                    {"href": "https://www.instagram.com/dawnflock/", "text": "Dawn Flock"},
                    {"href": "https://example.com/other", "text": "Other"},
                ],
            },
            latency_ms=230,
        )
        self.assertEqual(row["exact_profile_hits"], 1)
        self.assertFalse(row["can_confirm_claimability"])
        self.assertFalse(row["can_confirm_occupancy"])


class BrowserFusionTests(unittest.TestCase):
    def eye(self, signal, engine, confidence=0.92):
        return {"signal": signal, "engine": engine, "confidence": confidence}

    def base(self, status):
        return {
            "status": status,
            "detail": "fixture",
            "url": "https://www.instagram.com/dawnflock/",
            "source": "fixture",
            "method": "fixture",
            "confidence": 0.7,
            "occupancy": "not_found" if status == "not_found" else "unknown",
            "claimability": "confirmed" if status == "claimable" else "unconfirmed",
        }

    def test_double_browser_absence_never_becomes_claimable(self):
        merged, meta = merge_browser_platform(
            self.base("unknown"),
            self.eye("absent", "chromium"),
            self.eye("absent", "webkit"),
        )
        self.assertEqual(merged["status"], "not_found")
        self.assertEqual(merged["claimability"], "unconfirmed")
        self.assertEqual(meta["consensus"], "absent_two_engines")

    def test_existing_claimable_survives_agreeing_absence_as_claimable(self):
        merged, _ = merge_browser_platform(
            self.base("claimable"),
            self.eye("absent", "chromium"),
            self.eye("absent", "webkit"),
        )
        self.assertEqual(merged["status"], "claimable")

    def test_rendered_identity_contradicting_claimable_fails_closed(self):
        merged, meta = merge_browser_platform(
            self.base("claimable"),
            self.eye("exists", "chromium", 0.97),
            self.eye("exists", "webkit", 0.96),
        )
        self.assertEqual(merged["status"], "unknown")
        self.assertEqual(merged["claimability"], "unconfirmed")
        self.assertEqual(meta["consensus"], "exists")

    def test_search_hit_does_not_rewrite_availability_without_browser_presence(self):
        merged, meta = merge_browser_platform(
            self.base("not_found"),
            self.eye("absent", "chromium"),
            self.eye("absent", "webkit"),
            {"exact_profile_hits": 1},
        )
        self.assertEqual(merged["status"], "not_found")
        self.assertEqual(meta["search"]["exact_profile_hits"], 1)

    def test_candidate_ranking_is_refreshed_after_browser_fusion(self):
        row = {
            "name": "DawnFlock",
            "name_quality_score": 88,
            "availability": {"instagram": self.base("unknown")},
            "required_resources": ["instagram"],
        }
        enriched = apply_browser_enrichment(
            row,
            {"instagram": {
                "eye_a": self.eye("absent", "chromium"),
                "eye_b": self.eye("absent", "webkit"),
            }},
            ["instagram"],
        )
        self.assertEqual(enriched["availability"]["instagram"]["status"], "not_found")
        self.assertEqual(enriched["bundle_availability_state"], "promising")
        self.assertEqual(enriched["ranking_model"], "final-v1")
        self.assertIsInstance(enriched["final_score"], float)


class BrowserEnrichmentPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore("sqlite+pysqlite:///:memory:")
        self.events = DurableCandidateEventStore(self.store)
        self.session = self.store.create_session({
            "client_session_id": "browser-v3",
            "title": "browser-v3",
            "prompt_history": [],
            "resources": ["instagram"],
            "shortlist": [],
            "direction_anchors": [],
            "runs": [],
            "feedback": {},
            "batch_counter": 0,
            "created": "2026-08-20T00:00:00+00:00",
            "updated": "2026-08-20T00:00:00+00:00",
        })
        self.job = {
            "id": "job-browser-v3",
            "session_id": self.session["id"],
            "run_id": "run-browser-v3",
            "resources": ["instagram"],
            "required_resources": ["instagram"],
        }

    def test_enriched_row_is_durable_and_emits_incremental_event(self):
        staged = self.events.stage_candidates(self.job, [{"name": "DawnFlock"}], 1)[0]
        final = dict(staged)
        final.update({
            "availability": {
                "instagram": {
                    "status": "unknown", "detail": "fixture", "url": "", "source": "fixture",
                    "method": "fixture", "confidence": 0.2, "occupancy": "unknown",
                    "claimability": "unconfirmed",
                }
            },
            "verification": {},
            "checked": True,
        })
        completed = self.events.finalize_candidate(self.job, final, 1)
        enriched = apply_browser_enrichment(
            completed,
            {"instagram": {
                "eye_a": {"signal": "absent", "engine": "chromium", "confidence": 0.92},
                "eye_b": {"signal": "absent", "engine": "webkit", "confidence": 0.91},
            }},
            ["instagram"],
        )
        persisted = persist_browser_enrichment(self.events, self.job, enriched)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["availability"]["instagram"]["status"], "not_found")

        feed = self.events.since(self.session["id"], self.session["token"], 0, 20)
        types = [event["event_type"] for event in feed["events"]]
        self.assertEqual(types, ["candidate_generated", "candidate_completed", "candidate_enriched"])
        self.assertTrue(feed["events"][-1]["payload"]["row"]["checked"])


class VerificationPipelineContractTests(unittest.TestCase):
    def test_worker_queues_browser_enrichment_after_fast_runner(self):
        source = Path("worker_entry.py").read_text(encoding="utf-8")
        self.assertIn("install_live_background_queue(live_background)", source)
        self.assertIn("BROWSER_PIPELINE_WORKERS", source)
        self.assertIn("run_live_background_job", source)

    def test_browser_event_ui_and_cache_bust_are_live(self):
        source = Path("static/durable_live_events.js").read_text(encoding="utf-8")
        self.assertIn("candidate_enriched", source)
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('/static/durable_live_events.js?v=2', body)

    def test_diagnostics_expose_nonblocking_v3_order(self):
        diagnostics = app.test_client().get("/api/verification/diagnostics").get_json()
        pipeline = diagnostics["verification_pipeline"]
        self.assertEqual(pipeline["version"], "v3.1")
        self.assertTrue(pipeline["foreground_and_background_share_browser_pipe"])
        self.assertFalse(pipeline["fast_results_blocked_by_browser"])
        self.assertFalse(pipeline["browser_intelligence"]["browser_absence_can_decide_claimability"])
        self.assertTrue(RELEASE_MARKER.startswith("v8.12."))


if __name__ == "__main__":
    unittest.main()
