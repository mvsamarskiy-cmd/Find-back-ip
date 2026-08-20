import os
import threading
import unittest
from unittest.mock import patch

import browser_queue
from browser_queue import BrowserJobQueue
from session_store import SessionStore
from session_store_threadsafe import install_threadsafe_session_store


class BrowserQueueFastPathTests(unittest.TestCase):
    def setUp(self):
        install_threadsafe_session_store()
        self.env = patch.dict(os.environ, {"BROWSER_EYE_URL": "http://browser-eye.internal"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_repeated_polling_does_not_repeat_schema_check(self):
        store = SessionStore("sqlite+pysqlite:///:memory:")
        queue = BrowserJobQueue(store)
        original = browser_queue.browser_jobs.create
        calls = []

        def counted_create(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        with patch.object(browser_queue.browser_jobs, "create", side_effect=counted_create):
            first = queue._engine()
            for _ in range(20):
                self.assertIs(queue._engine(), first)

        self.assertEqual(len(calls), 1)
        self.assertTrue(queue.diagnostics()["schema_check_hot_path"] is False)

    def test_concurrent_first_poll_serializes_queue_table_readiness(self):
        store = SessionStore("sqlite+pysqlite:///:memory:")
        queue = BrowserJobQueue(store)
        original = browser_queue.browser_jobs.create
        calls = []
        errors = []
        barrier = threading.Barrier(5)

        def counted_create(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        def use_queue():
            try:
                barrier.wait(timeout=2)
                queue._engine()
            except Exception as error:
                errors.append(error)

        with patch.object(browser_queue.browser_jobs, "create", side_effect=counted_create):
            threads = [threading.Thread(target=use_queue) for _ in range(5)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)

        self.assertEqual(errors, [])
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
