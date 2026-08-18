import os
import unittest

from background_jobs import SearchJobStore, run_one_job
from session_store import SessionStore
from variant_store import VariantExpansionStore


@unittest.skipUnless(os.environ.get("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class PostgresSessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore(os.environ["TEST_POSTGRES_URL"])
        self.created = self.store.create_session({
            "client_session_id": "postgres-ci",
            "title": "Postgres CI",
            "prompt_history": [{"text": "cars warsaw", "at": "2026-08-18T10:00:00Z"}],
            "resources": ["com", "x"],
            "shortlist": [],
            "direction_anchors": [],
            "runs": [{"id": "r-ci", "prompt": "cars warsaw", "status": "running"}],
            "feedback": {},
            "batch_counter": 1,
            "created": "2026-08-18T09:00:00Z",
            "updated": "2026-08-18T10:00:00Z",
        })

    def tearDown(self):
        self.store.delete_session(self.created["id"], self.created["token"])

    def test_real_postgres_round_trip_and_idempotent_candidate_upsert(self):
        row = {
            "name": "GoldenMile",
            "checked": False,
            "received_seq": 1,
            "availability": {
                "com": {"status": "not_found", "source": "verisign_rdap"},
                "x": {"status": "checking", "source": "streaming_client"},
            },
            "verification": {"com": {"verdict": "likely_available"}},
        }
        self.store.upsert_candidates(self.created["id"], self.created["token"], [row])
        row["checked"] = True
        row["availability"]["x"] = {"status": "taken", "source": "socialscan"}
        self.store.upsert_candidates(self.created["id"], self.created["token"], [row])

        snapshot = self.store.load_session(self.created["id"], self.created["token"])
        self.assertEqual(snapshot["title"], "Postgres CI")
        self.assertEqual(len(snapshot["runs"]), 1)
        self.assertEqual(len(snapshot["results"]), 1)
        self.assertEqual(snapshot["results"][0]["availability"]["x"]["status"], "taken")
        self.assertTrue(snapshot["results"][0]["checked"])

    def test_real_postgres_background_queue_claim_checkpoint_and_complete(self):
        jobs = SearchJobStore(self.store)
        job = jobs.enqueue(self.created["id"], self.created["token"], {
            "prompt": "warsaw cars",
            "resources": ["com"],
            "required_resources": ["com"],
            "preferences": {},
            "search_context": {"mode": "new_brand", "brand_name": "", "guidance": ""},
            "generation_context": {},
            "target_count": 2,
            "batch_size": 2,
            "max_batches": 2,
        })
        self.assertEqual(job["state"], "pending")

        def generate(_job, _count, _context):
            return [{"name": "MileWawa"}, {"name": "VarsoMoto"}]

        def verify(_job, candidate):
            return {
                **candidate,
                "availability": {
                    "com": {
                        "status": "not_found",
                        "source": "verisign_rdap",
                        "method": "rdap",
                        "confidence": 0.8,
                        "occupancy": "not_found",
                        "claimability": "unconfirmed",
                    }
                },
                "verification": {"com": {"verdict": "likely_available"}},
                "bundle_state": "promising",
                "bundle_score": 40,
                "checked": True,
            }

        finished = run_one_job(jobs, "postgres-ci-worker", generate, verify)
        self.assertEqual(finished["state"], "completed")
        self.assertEqual(finished["stop_reason"], "target_reached")
        self.assertEqual(finished["delivered_count"], 2)

        snapshot = self.store.load_session(self.created["id"], self.created["token"])
        names = {row["name"] for row in snapshot["results"]}
        self.assertIn("MileWawa", names)
        self.assertIn("VarsoMoto", names)
        background_runs = [row for row in snapshot["runs"] if row.get("background_job_id") == job["id"]]
        self.assertEqual(len(background_runs), 1)
        self.assertEqual(background_runs[0]["status"], "completed")

    def test_real_postgres_variant_expansion_round_trip(self):
        variants = VariantExpansionStore(self.store)
        saved = variants.upsert(
            self.created["id"],
            self.created["token"],
            "GoldenMile",
            {
                "resources": ["x"],
                "options": {"underscore": True},
                "checked_at": "2026-08-19T00:00:00Z",
                "results": [{
                    "resource": "x",
                    "identifier": "_goldenmile",
                    "status": "not_found",
                    "strict_free": True,
                    "availability": {"status": "not_found", "source": "socialscan"},
                }],
            },
        )
        self.assertEqual(saved["parent_name"], "GoldenMile")
        self.assertFalse(saved["results"][0]["strict_free"])

        loaded = variants.get(self.created["id"], self.created["token"], "GoldenMile")
        self.assertEqual(loaded["results"][0]["identifier"], "_goldenmile")
        self.assertEqual(loaded["results"][0]["status"], "not_found")
        self.assertFalse(loaded["results"][0]["strict_free"])
        self.assertTrue(loaded.get("updated_at"))


if __name__ == "__main__":
    unittest.main()
