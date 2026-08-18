import unittest
from unittest.mock import patch

import background_search_api
import session_api
from background_jobs import SearchJobStore
from session_store import SessionStore
from telegram_bootstrap import app


class CandidateFeedApiTests(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore("sqlite+pysqlite:///:memory:")
        self.job_store = SearchJobStore(self.store)
        self.session_patch = patch.object(session_api, "STORE", self.store)
        self.job_patch = patch.object(background_search_api, "JOB_STORE", self.job_store)
        self.session_patch.start()
        self.job_patch.start()
        self.client = app.test_client()
        created = self.client.post("/api/sessions", json={
            "title": "candidate feed",
            "resources": ["com"],
            "prompt_history": [],
            "runs": [],
            "feedback": {},
        }).get_json()
        self.session_id = created["session_id"]
        self.token = created["session_token"]
        self.headers = {session_api.TOKEN_HEADER: self.token}
        self.store.upsert_candidates(self.session_id, self.token, [
            {"name": "One", "received_seq": 1, "availability": {}},
            {"name": "Two", "received_seq": 2, "availability": {}},
        ])

    def tearDown(self):
        self.job_patch.stop()
        self.session_patch.stop()

    def test_candidate_feed_returns_only_rows_after_cursor(self):
        response = self.client.get(
            f"/api/sessions/{self.session_id}/candidate-feed?after_seq=1&limit=100",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual([row["name"] for row in data["candidates"]], ["Two"])
        self.assertEqual(data["next_after_seq"], 2)

    def test_candidate_feed_requires_capability_and_bounded_page(self):
        denied = self.client.get(f"/api/sessions/{self.session_id}/candidate-feed?after_seq=0")
        self.assertEqual(denied.status_code, 404)
        oversized = self.client.get(
            f"/api/sessions/{self.session_id}/candidate-feed?after_seq=0&limit=201",
            headers=self.headers,
        )
        self.assertEqual(oversized.status_code, 400)


if __name__ == "__main__":
    unittest.main()
