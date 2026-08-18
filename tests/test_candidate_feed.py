import unittest

from candidate_feed import CandidateFeedStore
from session_store import SessionStore


class CandidateFeedTests(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore("sqlite+pysqlite:///:memory:")
        self.created = self.store.create_session({
            "title": "feed",
            "resources": ["com"],
            "prompt_history": [],
            "runs": [],
            "feedback": {},
        })
        self.feed = CandidateFeedStore(self.store)
        self.store.upsert_candidates(self.created["id"], self.created["token"], [
            {"name": "First", "received_seq": 1, "availability": {}},
            {"name": "Second", "received_seq": 2, "availability": {}},
            {"name": "Third", "received_seq": 3, "availability": {}},
        ])

    def test_since_is_ascending_incremental_and_reports_more(self):
        page = self.feed.since(self.created["id"], self.created["token"], after_seq=1, limit=1)
        self.assertEqual([row["name"] for row in page["candidates"]], ["Second"])
        self.assertEqual(page["next_after_seq"], 2)
        self.assertTrue(page["has_more"])

        last = self.feed.since(self.created["id"], self.created["token"], after_seq=2, limit=10)
        self.assertEqual([row["name"] for row in last["candidates"]], ["Third"])
        self.assertEqual(last["next_after_seq"], 3)
        self.assertFalse(last["has_more"])

    def test_wrong_capability_token_cannot_read_feed(self):
        self.assertIsNone(self.feed.since(self.created["id"], "wrong", after_seq=0, limit=100))


if __name__ == "__main__":
    unittest.main()
