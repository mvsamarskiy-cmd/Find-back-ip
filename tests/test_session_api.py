import unittest
from unittest.mock import patch

import session_api
from session_store import SessionStore
from telegram_bootstrap import app


class SessionApiTests(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore("sqlite+pysqlite:///:memory:")
        self.patcher = patch.object(session_api, "STORE", self.store)
        self.patcher.start()
        self.client = app.test_client()
        self.metadata = {
            "client_session_id": "s-local",
            "title": "Warsaw cars",
            "prompt_history": [{"text": "cars warsaw", "at": "2026-08-18T10:00:00Z"}],
            "resources": ["x"],
            "runs": [{"id": "r1", "prompt": "cars warsaw", "status": "running"}],
            "feedback": {"goldenmile": {"vote": 1, "comment": "гарно"}},
            "batch_counter": 1,
            "created": "2026-08-18T09:00:00Z",
            "updated": "2026-08-18T10:00:00Z",
        }

    def tearDown(self):
        self.patcher.stop()

    def _create(self):
        response = self.client.post("/api/sessions", json=self.metadata)
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    @staticmethod
    def _headers(created):
        return {session_api.TOKEN_HEADER: created["session_token"]}

    def test_capabilities_report_normalized_storage_without_secrets(self):
        response = self.client.get("/api/session-storage")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["backend"], "sqlite")
        self.assertIn("candidate", payload["normalized_entities"])
        self.assertNotIn("database_url", payload)

    def test_create_and_load_requires_capability_token(self):
        created = self._create()
        missing = self.client.get("/api/sessions/" + created["session_id"])
        self.assertEqual(missing.status_code, 404)

        loaded = self.client.get(
            "/api/sessions/" + created["session_id"],
            headers=self._headers(created),
        )
        self.assertEqual(loaded.status_code, 200)
        snapshot = loaded.get_json()["session"]
        self.assertEqual(snapshot["title"], "Warsaw cars")
        self.assertEqual(snapshot["feedback"]["goldenmile"]["vote"], 1)

    def test_candidate_batch_is_idempotent_and_preserves_latest_evidence(self):
        created = self._create()
        path = "/api/sessions/" + created["session_id"] + "/candidates/batch"
        first = {
            "name": "GoldenMile",
            "checked": False,
            "received_seq": 1,
            "availability": {"x": {"status": "checking", "source": "streaming_client"}},
        }
        second = {
            "name": "GoldenMile",
            "checked": True,
            "received_seq": 1,
            "availability": {"x": {"status": "taken", "source": "socialscan"}},
        }
        self.assertEqual(
            self.client.post(path, json={"candidates": [first]}, headers=self._headers(created)).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(path, json={"candidates": [second]}, headers=self._headers(created)).status_code,
            200,
        )
        loaded = self.client.get(
            "/api/sessions/" + created["session_id"],
            headers=self._headers(created),
        ).get_json()["session"]
        self.assertEqual(len(loaded["results"]), 1)
        self.assertEqual(loaded["results"][0]["availability"]["x"]["status"], "taken")

    def test_update_metadata_does_not_duplicate_runs(self):
        created = self._create()
        path = "/api/sessions/" + created["session_id"]
        updated = dict(self.metadata)
        updated["runs"] = [{"id": "r1", "prompt": "cars warsaw", "status": "complete"}]
        headers = self._headers(created)
        self.assertEqual(self.client.put(path, json=updated, headers=headers).status_code, 200)
        self.assertEqual(self.client.put(path, json=updated, headers=headers).status_code, 200)
        loaded = self.client.get(path, headers=headers).get_json()["session"]
        self.assertEqual(len(loaded["runs"]), 1)
        self.assertEqual(loaded["runs"][0]["status"], "complete")

    def test_candidate_batch_is_bounded(self):
        created = self._create()
        path = "/api/sessions/" + created["session_id"] + "/candidates/batch"
        rows = [{"name": f"Name{i}", "availability": {}} for i in range(session_api.MAX_CANDIDATE_BATCH + 1)]
        response = self.client.post(path, json={"candidates": rows}, headers=self._headers(created))
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
