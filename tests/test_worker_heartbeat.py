import unittest

from session_store import SessionStore
from worker_heartbeat import beat, remove, status


class WorkerHeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore("sqlite+pysqlite:///:memory:")
        self.store.ensure_ready()

    def test_heartbeat_marks_worker_online_without_exposing_identity(self):
        beat(self.store, "worker-secret-ish-id")
        state = status(self.store)
        self.assertTrue(state["worker_online"])
        self.assertEqual(state["worker_count"], 1)
        self.assertIsNotNone(state["last_seen_at"])
        self.assertNotIn("worker_id", state)

    def test_clean_shutdown_removes_worker(self):
        beat(self.store, "worker-1")
        remove(self.store, "worker-1")
        state = status(self.store)
        self.assertFalse(state["worker_online"])
        self.assertEqual(state["worker_count"], 0)


if __name__ == "__main__":
    unittest.main()
