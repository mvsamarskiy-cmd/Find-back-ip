from datetime import timedelta
import unittest

from durable_candidate_events import DurableCandidateEventStore
from session_store import SessionStore, _utcnow


class DurableEventSequenceTests(unittest.TestCase):
    def test_cursor_never_resets_after_transient_events_are_pruned(self):
        session_store = SessionStore("sqlite+pysqlite:///:memory:")
        events = DurableCandidateEventStore(session_store)
        created = session_store.create_session({
            "client_session_id": "cursor-retention",
            "title": "cursor",
            "prompt_history": [],
            "resources": ["telegram"],
            "shortlist": [],
            "direction_anchors": [],
            "runs": [],
            "feedback": {},
            "batch_counter": 0,
            "created": _utcnow().isoformat(),
            "updated": _utcnow().isoformat(),
        })
        job = {
            "id": "11111111-1111-1111-1111-111111111111",
            "session_id": created["id"],
            "run_id": "r-live",
            "resources": ["telegram"],
        }

        events.stage_candidates(job, [{"name": "Firstlive"}], 1)
        first = events.since(created["id"], created["token"], 0, 100)
        old_cursor = first["next_after_seq"]
        self.assertGreater(old_cursor, 0)

        removed = events.prune_expired(_utcnow() + timedelta(days=8))
        self.assertEqual(removed, 1)

        events.stage_candidates(job, [{"name": "Secondlive"}], 2)
        second = events.since(created["id"], created["token"], old_cursor, 100)
        self.assertEqual(len(second["events"]), 1)
        self.assertEqual(second["events"][0]["name_key"], "secondlive")
        self.assertGreater(second["events"][0]["event_seq"], old_cursor)


if __name__ == "__main__":
    unittest.main()
