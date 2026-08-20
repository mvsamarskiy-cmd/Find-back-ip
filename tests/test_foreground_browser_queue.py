import os
from pathlib import Path
import unittest
from unittest.mock import patch

from sqlalchemy import select, update

from browser_pipeline_worker import SynchronousBrowserRuntimeAdapter
from browser_queue import BrowserJobQueue, browser_jobs, install_candidate_enqueue
from session_store import SessionStore, _utcnow, candidates
from telegram_bootstrap import RELEASE_MARKER, app


class ForegroundBrowserQueueTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"BROWSER_EYE_URL": "http://browser-eye.internal"})
        self.env.start()
        self.store = SessionStore("sqlite+pysqlite:///:memory:")
        self.queue = BrowserJobQueue(self.store)
        self.session = self.store.create_session({
            "client_session_id": "fg-browser",
            "title": "fg-browser",
            "prompt_history": [],
            "resources": ["instagram", "youtube"],
            "shortlist": [],
            "direction_anchors": [],
            "runs": [],
            "feedback": {},
            "batch_counter": 0,
            "created": "2026-08-20T00:00:00Z",
            "updated": "2026-08-20T00:00:00Z",
        })

    def tearDown(self):
        self.env.stop()

    @staticmethod
    def candidate(name="DawnFlock", run_id="r1", status="not_found"):
        return {
            "name": name,
            "checked": True,
            "run_id": run_id,
            "final_score": 82.0,
            "availability": {
                "instagram": {
                    "status": status,
                    "detail": "fixture",
                    "url": "https://instagram.com/dawnflock/",
                    "source": "fixture",
                    "method": "fixture",
                    "confidence": 0.7,
                    "occupancy": "not_found" if status == "not_found" else "unknown",
                    "claimability": "unconfirmed",
                },
                "youtube": {
                    "status": "unknown",
                    "detail": "fixture",
                    "url": "https://youtube.com/@dawnflock",
                    "source": "fixture",
                    "method": "fixture",
                    "confidence": 0.0,
                    "occupancy": "unknown",
                    "claimability": "unconfirmed",
                },
            },
            "verification": {},
        }

    def test_candidate_mirror_write_enqueues_without_changing_api_contract(self):
        install_candidate_enqueue(self.store, self.queue)
        row = self.candidate()
        updated = self.store.upsert_candidates(self.session["id"], self.session["token"], [row])
        self.assertEqual(updated["accepted"], 1)
        self.assertEqual(self.queue.counts()["pending"], 1)

        claimed = self.queue.claim_next("pump-1")
        self.assertEqual(claimed["candidate"]["name"], "DawnFlock")
        self.assertEqual(set(claimed["resources"]), {"instagram", "youtube"})
        self.assertEqual(claimed["state"] if "state" in claimed else "running", "running")

    def test_hard_conflict_exits_before_expensive_browser_pipe(self):
        install_candidate_enqueue(self.store, self.queue)
        row = self.candidate(status="taken")
        self.store.upsert_candidates(self.session["id"], self.session["token"], [row])
        self.assertEqual(self.queue.counts()["pending"], 0)

    def test_same_run_stale_client_cannot_erase_completed_server_browser_facts(self):
        row = self.candidate()
        self.store.upsert_candidates(self.session["id"], self.session["token"], [row])
        engine = self.store._ensure_engine()
        enriched = dict(row)
        enriched["availability"] = {
            **row["availability"],
            "instagram": {
                **row["availability"]["instagram"],
                "status": "not_found",
                "confidence": 0.95,
                "source": "browser_fusion",
            },
        }
        enriched["browser_verification_state"] = "complete"
        enriched["browser_enriched_at"] = "2026-08-20T10:00:00Z"
        enriched["browser_verification"] = {
            "instagram": {"consensus": "absent_two_engines", "double_checked": True}
        }
        enriched["final_score"] = 87.5
        with engine.begin() as conn:
            conn.execute(
                update(candidates)
                .where(
                    (candidates.c.session_id == self.session["id"])
                    & (candidates.c.name_key == "dawnflock")
                )
                .values(row=enriched, updated_at=_utcnow())
            )

        stale = self.candidate()
        stale["final_score"] = 82.0
        merged = self.queue.preserve_server_enrichment(self.session["id"], [stale])[0]
        self.assertEqual(merged["browser_verification_state"], "complete")
        self.assertEqual(merged["browser_verification"]["instagram"]["consensus"], "absent_two_engines")
        self.assertEqual(merged["final_score"], 87.5)
        self.assertEqual(merged["availability"]["instagram"]["source"], "browser_fusion")

    def test_new_run_can_recheck_same_spelling(self):
        install_candidate_enqueue(self.store, self.queue)
        first = self.candidate(run_id="r1")
        self.store.upsert_candidates(self.session["id"], self.session["token"], [first])
        claim = self.queue.claim_next("pump-1")
        self.queue.complete(claim["session_id"], claim["name_key"])

        second = self.candidate(run_id="r2")
        self.store.upsert_candidates(self.session["id"], self.session["token"], [second])
        claimed = self.queue.claim_next("pump-2")
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["run_id"], "r2")


class RuntimeAdapterTests(unittest.TestCase):
    def test_adapter_reports_success_after_durable_enrichment(self):
        class Runtime:
            base_url = "http://browser-eye.internal"
            def _run(self, job, row, event_store):
                return {"name": row["name"], "browser_verification_state": "complete"}
            def _failed(self):
                raise AssertionError("must not fail")

        calls = []
        adapter = SynchronousBrowserRuntimeAdapter(Runtime())
        accepted = adapter.submit(
            {"session_id": "s", "name_key": "n"},
            {"name": "N"},
            object(),
            on_done=lambda success, error: calls.append((success, error)),
        )
        self.assertTrue(accepted)
        self.assertEqual(calls, [(True, None)])


class ForegroundBrowserPipelineContractTests(unittest.TestCase):
    def test_web_diagnostics_expose_shared_nonblocking_pipe(self):
        diagnostics = app.test_client().get("/api/verification/diagnostics").get_json()
        pipeline = diagnostics["verification_pipeline"]
        self.assertEqual(pipeline["version"], "v3.1")
        self.assertTrue(pipeline["foreground_and_background_share_browser_pipe"])
        self.assertFalse(pipeline["fast_results_blocked_by_browser"])
        self.assertFalse(pipeline["browser_queue"]["foreground_stream_blocking"])
        self.assertIn("durable_candidate_boundary", pipeline["order"])
        self.assertTrue(RELEASE_MARKER.startswith("v8.12."))

    def test_worker_uses_durable_queue_instead_of_direct_browser_wrapper(self):
        source = Path("worker_entry.py").read_text(encoding="utf-8")
        self.assertIn("install_live_background_queue(live_background)", source)
        self.assertIn("BROWSER_PIPELINE_WORKERS", source)
        self.assertIn("pump_main", source)
        self.assertNotIn("install_live_background_enrichment", source)

    def test_foreground_enqueue_is_installed_before_session_routes(self):
        source = Path("telegram_bootstrap.py").read_text(encoding="utf-8")
        enqueue = source.index("install_candidate_enqueue(session_api_module.STORE)")
        routes = source.index("install_session_routes(app, app_module)")
        self.assertLess(enqueue, routes)


if __name__ == "__main__":
    unittest.main()
