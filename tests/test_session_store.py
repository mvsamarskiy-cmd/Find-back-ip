import unittest

from sqlalchemy import select

from session_store import SessionStore, evidence


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore("sqlite+pysqlite:///:memory:")
        self.metadata = {
            "client_session_id": "s-local",
            "title": "Warsaw cars",
            "prompt_history": [{"text": "cars warsaw", "at": "2026-08-18T10:00:00Z", "feedback": []}],
            "resources": ["com", "x"],
            "shortlist": ["GoldenMile"],
            "direction_anchors": ["MotorMile"],
            "runs": [{"id": "r1", "prompt": "cars warsaw", "status": "running"}],
            "feedback": {"goldenmile": {"vote": 1, "comment": "гарно"}},
            "batch_counter": 4,
            "created": "2026-08-18T09:00:00Z",
            "updated": "2026-08-18T10:00:00Z",
        }
        self.created = self.store.create_session(self.metadata)

    def test_capability_token_is_required(self):
        self.assertIsNone(self.store.load_session(self.created["id"], "wrong-token"))
        snapshot = self.store.load_session(self.created["id"], self.created["token"])
        self.assertEqual(snapshot["title"], "Warsaw cars")
        self.assertEqual(snapshot["feedback"]["goldenmile"]["vote"], 1)

    def test_metadata_runs_and_feedback_upsert_idempotently(self):
        payload = dict(self.metadata)
        payload["runs"] = [{"id": "r1", "prompt": "cars warsaw", "status": "complete"}]
        payload["feedback"] = {"goldenmile": {"vote": 1, "comment": "дуже гарно"}}
        first = self.store.update_session(self.created["id"], self.created["token"], payload)
        second = self.store.update_session(self.created["id"], self.created["token"], payload)
        self.assertGreater(second["revision"], first["revision"])
        snapshot = self.store.load_session(self.created["id"], self.created["token"])
        self.assertEqual(len(snapshot["runs"]), 1)
        self.assertEqual(snapshot["runs"][0]["status"], "complete")
        self.assertEqual(snapshot["feedback"]["goldenmile"]["comment"], "дуже гарно")

    def test_candidates_and_resource_evidence_are_upserted_without_duplicates(self):
        row = {
            "name": "GoldenMile",
            "checked": False,
            "received_seq": 7,
            "availability": {
                "x": {"status": "checking", "source": "streaming_client"},
                "com": {"status": "not_found", "source": "verisign_rdap"},
            },
            "verification": {"com": {"verdict": "likely_available"}},
        }
        first = self.store.upsert_candidates(self.created["id"], self.created["token"], [row])
        row["checked"] = True
        row["availability"]["x"] = {"status": "taken", "source": "socialscan"}
        second = self.store.upsert_candidates(self.created["id"], self.created["token"], [row])
        self.assertGreater(second["revision"], first["revision"])

        snapshot = self.store.load_session(self.created["id"], self.created["token"])
        self.assertEqual(len(snapshot["results"]), 1)
        self.assertTrue(snapshot["results"][0]["checked"])
        self.assertEqual(snapshot["results"][0]["availability"]["x"]["status"], "taken")

        with self.store._engine.connect() as conn:
            evidence_rows = conn.execute(select(evidence)).mappings().all()
        self.assertEqual(len(evidence_rows), 2)
        by_resource = {row["resource"]: row for row in evidence_rows}
        self.assertEqual(by_resource["x"]["availability"]["status"], "taken")
        self.assertEqual(by_resource["com"]["verification"]["verdict"], "likely_available")

    def test_diagnostics_never_expose_database_url(self):
        diagnostics = self.store.diagnostics()
        self.assertEqual(diagnostics["backend"], "sqlite")
        self.assertNotIn("database_url", diagnostics)
        self.assertIn("evidence", diagnostics["normalized_entities"])


if __name__ == "__main__":
    unittest.main()
