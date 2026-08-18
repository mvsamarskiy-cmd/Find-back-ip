import os
import unittest

from session_store import SessionStore


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


if __name__ == "__main__":
    unittest.main()
