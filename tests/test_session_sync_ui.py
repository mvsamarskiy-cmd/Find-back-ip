from pathlib import Path
import unittest

from telegram_bootstrap import app


class SessionSyncUiTests(unittest.TestCase):
    def test_home_loads_session_sync_after_streaming_layers(self):
        response = app.test_client().get("/")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('/static/streaming.js', body)
        self.assertIn('/static/resource_progress.js', body)
        self.assertIn('/static/session_sync.js', body)
        self.assertLess(body.index('/static/streaming.js'), body.index('/static/resource_progress.js'))
        self.assertLess(body.index('/static/resource_progress.js'), body.index('/static/session_sync.js'))

    def test_sync_client_is_best_effort_and_incremental(self):
        source = Path("static/session_sync.js").read_text(encoding="utf-8")
        self.assertIn("/api/session-storage", source)
        self.assertIn("/candidates/batch", source)
        self.assertIn("candidateQueue", source)
        self.assertIn("saveCurrentWithDurableMirror", source)
        self.assertIn("pagehide", source)
        self.assertIn("X-NameMachine-Session-Token", source)
        self.assertNotIn("session_token:", source)


if __name__ == "__main__":
    unittest.main()
