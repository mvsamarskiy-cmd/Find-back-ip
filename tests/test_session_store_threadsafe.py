import threading
import time
import unittest
from unittest.mock import patch

import session_store
from session_store import SessionStore
from session_store_threadsafe import install_threadsafe_session_store


class SessionStoreThreadsafeInitTests(unittest.TestCase):
    def test_concurrent_first_use_runs_schema_initialization_once(self):
        install_threadsafe_session_store()
        store = SessionStore("sqlite+pysqlite:///:memory:")
        original = session_store.metadata.create_all
        calls = []
        calls_lock = threading.Lock()

        def slow_create_all(engine):
            with calls_lock:
                calls.append(threading.current_thread().name)
            time.sleep(0.04)
            return original(engine)

        errors = []
        barrier = threading.Barrier(6)

        def initialize():
            try:
                barrier.wait(timeout=2)
                store._ensure_engine()
            except Exception as error:
                errors.append(error)

        with patch.object(session_store.metadata, "create_all", side_effect=slow_create_all):
            threads = [threading.Thread(target=initialize, name=f"init-{i}") for i in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)

        self.assertEqual(errors, [])
        self.assertEqual(len(calls), 1)
        self.assertTrue(store._initialized)
        self.assertIsNotNone(store._engine)

    def test_worker_installs_guard_before_concurrent_subsystems(self):
        source = open("worker_entry.py", encoding="utf-8").read()
        install_at = source.index("install_threadsafe_session_store()")
        audit_import = source.index("from audit_store import AUDIT_STORE")
        self.assertLess(install_at, audit_import)


if __name__ == "__main__":
    unittest.main()
