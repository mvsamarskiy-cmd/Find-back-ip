import unittest

from background_jobs import SearchJobStore, run_one_job
from session_store import SessionStore


class BackgroundSearchJobTests(unittest.TestCase):
    def setUp(self):
        self.session_store = SessionStore("sqlite+pysqlite:///:memory:")
        self.created = self.session_store.create_session({
            "client_session_id": "local-1",
            "title": "Warsaw cars",
            "prompt_history": [],
            "resources": ["com"],
            "shortlist": [],
            "direction_anchors": [],
            "runs": [],
            "feedback": {},
            "batch_counter": 0,
        })
        self.jobs = SearchJobStore(self.session_store)

    def enqueue(self, **overrides):
        payload = {
            "prompt": "cars warsaw",
            "resources": ["com"],
            "required_resources": ["com"],
            "preferences": {},
            "search_context": {"mode": "new_brand", "brand_name": "", "guidance": ""},
            "generation_context": {},
            "target_count": 3,
            "batch_size": 2,
            "max_batches": 4,
        }
        payload.update(overrides)
        return self.jobs.enqueue(self.created["id"], self.created["token"], payload)

    @staticmethod
    def verify(_job, candidate):
        row = dict(candidate)
        row.update({
            "availability": {
                "com": {
                    "status": "claimable",
                    "detail": "fixture",
                    "source": "fixture_registrar",
                    "method": "fixture",
                    "confidence": 1.0,
                    "occupancy": "not_found",
                    "claimability": "confirmed",
                }
            },
            "verification": {},
            "bundle_state": "confirmed",
            "bundle_score": 100,
            "checked": True,
        })
        return row

    def test_queue_requires_session_capability(self):
        denied = self.jobs.enqueue(self.created["id"], "wrong-token", {
            "prompt": "cars", "resources": ["com"], "required_resources": ["com"]
        })
        self.assertIsNone(denied)

    def test_worker_checkpoints_and_deduplicates_across_batches(self):
        self.enqueue()
        calls = []

        def generate(_job, _count, context):
            calls.append(context)
            if len(calls) == 1:
                return [{"name": "GoldenMile"}, {"name": "MotorMile"}]
            return [{"name": "MotorMile"}, {"name": "OpenMile"}]

        result = run_one_job(self.jobs, "worker-1", generate, self.verify)
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["stop_reason"], "target_reached")
        self.assertEqual(result["delivered_count"], 3)
        self.assertEqual(result["attempted_batches"], 2)
        self.assertIn("GoldenMile", calls[1]["exclude_names"])

        snapshot = self.session_store.load_session(self.created["id"], self.created["token"])
        names = [row["name"] for row in snapshot["results"]]
        self.assertEqual(names, ["GoldenMile", "MotorMile", "OpenMile"])
        self.assertEqual(len(snapshot["runs"]), 1)
        self.assertEqual(snapshot["runs"][0]["status"], "completed")

    def test_candidate_verifier_failure_is_persisted_as_unknown_not_lost(self):
        self.enqueue(target_count=1, batch_size=1, max_batches=1)

        def generate(_job, _count, _context):
            return [{"name": "MileWawa"}]

        def broken_verify(_job, _candidate):
            raise RuntimeError("fixture failure")

        result = run_one_job(self.jobs, "worker-2", generate, broken_verify)
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["delivered_count"], 1)
        snapshot = self.session_store.load_session(self.created["id"], self.created["token"])
        row = snapshot["results"][0]
        self.assertEqual(row["availability"]["com"]["status"], "unknown")
        self.assertFalse(row["checked"])

    def test_pending_job_can_be_cancelled_without_worker(self):
        job = self.enqueue(target_count=50)
        cancelled = self.jobs.cancel(self.created["id"], self.created["token"], job["id"])
        self.assertEqual(cancelled["state"], "cancelled")
        self.assertEqual(cancelled["stop_reason"], "user_cancelled")
        self.assertIsNone(self.jobs.claim_next("worker-3"))

    def test_worker_shutdown_returns_job_to_pending_for_resume(self):
        job = self.enqueue(target_count=5, batch_size=2)
        result = run_one_job(
            self.jobs,
            "worker-4",
            lambda _job, _count, _context: [{"name": "NeverRuns"}],
            self.verify,
            should_stop=lambda: True,
        )
        self.assertEqual(result["id"], job["id"])
        self.assertEqual(result["state"], "pending")
        self.assertEqual(result["stop_reason"], "worker_shutdown")
        reclaimed = self.jobs.claim_next("worker-5")
        self.assertEqual(reclaimed["id"], job["id"])
        self.assertEqual(reclaimed["state"], "running")


if __name__ == "__main__":
    unittest.main()
