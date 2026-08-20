from pathlib import Path
import unittest
from unittest.mock import patch

from availability_hunter import HUNTER_KEY
from background_jobs import SearchJobStore
from durable_candidate_events import DurableCandidateEventStore
from live_background import run_live_background_job
from session_store import SessionStore
from telegram_bootstrap import RELEASE_MARKER, app


def create_session(store):
    return store.create_session({
        "client_session_id": "s-live-test",
        "title": "live",
        "prompt_history": [],
        "resources": ["telegram"],
        "shortlist": [],
        "direction_anchors": [],
        "runs": [],
        "feedback": {},
        "batch_counter": 0,
        "created": "2026-08-18T20:00:00+00:00",
        "updated": "2026-08-18T20:00:00+00:00",
    })


def final_row(candidate, status="taken"):
    row = dict(candidate)
    row.update({
        "availability": {
            "telegram": {
                "status": status,
                "detail": "fixture",
                "url": "https://t.me/" + str(candidate["name"]).lower(),
                "source": "fixture",
                "method": "fixture",
                "confidence": 1.0,
                "occupancy": "occupied" if status == "taken" else "absent",
                "claimability": "verified" if status == "claimable" else "unconfirmed",
            }
        },
        "verification": {},
        "bundle_state": "confirmed" if status == "claimable" else "conflict",
        "bundle_score": 1.0 if status == "claimable" else 0.0,
        "checked": True,
    })
    return row


class DurableCandidateEventStoreTests(unittest.TestCase):
    def setUp(self):
        self.session_store = SessionStore("sqlite+pysqlite:///:memory:")
        self.queue = SearchJobStore(self.session_store)
        self.events = DurableCandidateEventStore(self.session_store)
        self.created = create_session(self.session_store)

    def enqueue(self, **overrides):
        payload = {
            "run_id": "bg-live-1",
            "prompt": "bottle",
            "resources": ["telegram"],
            "required_resources": ["telegram"],
            "preferences": {},
            "search_context": {},
            "generation_context": {},
            "target_count": 2,
            "batch_size": 2,
            "max_batches": 2,
        }
        payload.update(overrides)
        return self.queue.enqueue(self.created["id"], self.created["token"], payload)

    def test_generated_is_durable_before_completed_and_order_is_stable(self):
        self.enqueue(max_batches=1)

        def generate(job, count, context):
            return [
                {"name": "Botanell", "reason": "one", "family": "root_blend"},
                {"name": "Glasetta", "reason": "two", "family": "invented_phonetic"},
            ][:count]

        def verify(job, candidate):
            return final_row(candidate, "taken")

        with patch("live_background.LIVE_CANDIDATES", self.events):
            result = run_live_background_job(
                self.queue,
                "worker-live",
                generate,
                verify,
                verify_workers=2,
            )

        self.assertEqual(result["state"], "completed")
        feed = self.events.since(self.created["id"], self.created["token"], 0, 100)
        event_types = [event["event_type"] for event in feed["events"]]
        self.assertEqual(event_types[:2], ["candidate_generated", "candidate_generated"])
        self.assertEqual(event_types.count("candidate_completed"), 2)

        generated = {
            event["name_key"]: event["payload"]["row"]
            for event in feed["events"] if event["event_type"] == "candidate_generated"
        }
        completed = {
            event["name_key"]: event["payload"]["row"]
            for event in feed["events"] if event["event_type"] == "candidate_completed"
        }
        self.assertEqual(set(generated), set(completed))
        for key in generated:
            self.assertFalse(generated[key]["checked"])
            self.assertEqual(generated[key]["verification_state"], "checking")
            self.assertEqual(generated[key]["availability"]["telegram"]["status"], "checking")
            self.assertTrue(completed[key]["checked"])
            self.assertEqual(completed[key]["verification_state"], "complete")
            self.assertEqual(generated[key]["received_seq"], completed[key]["received_seq"])

    def test_event_feed_is_capability_protected_and_cursor_incremental(self):
        self.enqueue(target_count=1, batch_size=1, max_batches=1)
        claimed = self.queue.claim_next("worker-cursor")
        staged = self.events.stage_candidates(claimed, [{"name": "Botavess"}], 1)
        self.assertEqual(len(staged), 1)
        first = self.events.since(self.created["id"], self.created["token"], 0, 1)
        self.assertEqual(len(first["events"]), 1)
        self.assertIsNone(self.events.since(self.created["id"], "wrong-token", 0, 10))
        after = first["next_after_seq"]
        finalized = self.events.finalize_candidate(claimed, final_row(staged[0], "taken"), 1)
        self.assertIsNotNone(finalized)
        second = self.events.since(self.created["id"], self.created["token"], after, 10)
        self.assertEqual([event["event_type"] for event in second["events"]], ["candidate_completed"])

    def test_hunter_keeps_strict_match_goal_with_live_events(self):
        self.enqueue(
            target_count=2,
            batch_size=2,
            search_context={
                HUNTER_KEY: {
                    "enabled": True,
                    "target_matches": 1,
                    "max_checks": 2,
                    "match_policy": "claimable",
                }
            },
        )

        def generate(job, count, context):
            return [{"name": "Freeone"}, {"name": "Busyone"}][:count]

        def verify(job, candidate):
            return final_row(candidate, "claimable" if candidate["name"] == "Freeone" else "taken")

        with patch("live_background.LIVE_CANDIDATES", self.events):
            result = run_live_background_job(
                self.queue,
                "worker-hunter-live",
                generate,
                verify,
                verify_workers=2,
            )
        self.assertEqual(result["stop_reason"], "target_matches_reached")
        runtime = (result.get("preferences") or {}).get("_hunter_runtime") or {}
        self.assertGreaterEqual(int(runtime.get("matches") or 0), 1)


class DurableLiveUiTests(unittest.TestCase):
    def test_real_lifecycle_consumer_is_loaded_after_card_wrappers(self):
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('/static/brand_collision_ui.js?v=1', body)
        self.assertIn('/static/durable_live_events.js?v=2', body)
        self.assertLess(
            body.index('/static/brand_collision_ui.js?v=1'),
            body.index('/static/durable_live_events.js?v=2'),
        )
        source = Path("static/durable_live_events.js").read_text(encoding="utf-8")
        self.assertIn("candidate_generated", source)
        self.assertIn("candidate_completed", source)
        self.assertIn("candidate_enriched", source)
        self.assertIn("verification_state = 'checking'", source)
        self.assertIn("candidate-events?after_seq=", source)
        self.assertNotIn("Math.random", source)

    def test_worker_entry_switches_production_runner_without_fake_progress(self):
        source = Path("worker_entry.py").read_text(encoding="utf-8")
        self.assertIn("run_live_background_job", source)
        self.assertIn("search_worker.run_availability_hunter_job = run_live_background_job", source)
        self.assertIn("install_live_background_queue(live_background)", source)
        self.assertIn("BROWSER_PIPELINE_WORKERS", source)
        runner = Path("live_background.py").read_text(encoding="utf-8")
        self.assertIn("stage_candidates", runner)
        self.assertIn("finalize_candidate", runner)
        self.assertIn("as_completed", runner)

    def test_release_and_diagnostics_expose_durable_live_feed(self):
        self.assertTrue(RELEASE_MARKER.startswith("v8."))
        diagnostics = app.test_client().get("/api/verification/diagnostics").get_json()
        live = diagnostics["durable_candidate_events"]
        self.assertTrue(live["durable_live_events"])
        self.assertEqual(live["retention_days"], 7)
        self.assertEqual(
            diagnostics["background_search_ui"]["candidate_lifecycle_endpoint"],
            "/api/sessions/<session_id>/candidate-events",
        )


if __name__ == "__main__":
    unittest.main()