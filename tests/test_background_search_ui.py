from pathlib import Path
import unittest

from telegram_bootstrap import app


class BackgroundSearchUiTests(unittest.TestCase):
    def test_large_search_client_loads_after_session_sync_before_feed_navigation(self):
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('/static/background_search.js', body)
        self.assertLess(body.index('/static/session_sync.js'), body.index('/static/background_search.js'))
        self.assertLess(body.index('/static/background_search.js'), body.index('/static/feed_navigation.js'))

    def test_controls_are_hidden_until_worker_is_ready(self):
        source = Path("static/background_search.js").read_text(encoding="utf-8")
        self.assertIn("capability?.ready", source)
        self.assertIn("panel.hidden", source)
        self.assertIn("candidate-feed?after_seq=", source)
        self.assertIn("20000", source)
        self.assertIn("Можна закрити сторінку", source)

    def test_remote_candidates_are_merged_without_echo_sync(self):
        source = Path("static/background_search.js").read_text(encoding="utf-8")
        self.assertIn("write(SESSION_KEY, current)", source)
        self.assertIn("received_seq", source)
        self.assertIn("current.streamCounter", source)
        self.assertNotIn("saveCurrent(); // remote-origin", source)

    def test_live_telemetry_exposes_clock_quality_counts_and_feedback_reaction(self):
        source = Path("static/background_search.js").read_text(encoding="utf-8")
        self.assertIn('largeSearchClock', source)
        self.assertIn('largeSearchGreen', source)
        self.assertIn('largeSearchPromising', source)
        self.assertIn('largeSearchConflicts', source)
        self.assertIn('worker зчитав зміни', source)
        self.assertIn('worker_feedback_applied', source)

    def test_export_is_a_detailed_live_audit_not_legacy_100_result_summary(self):
        source = Path("static/background_search.js").read_text(encoding="utf-8")
        self.assertIn('NameMachine LIVE AUDIT REPORT', source)
        self.assertIn('ACTION / REACTION TIMELINE', source)
        self.assertIn('CANDIDATE LEDGER', source)
        self.assertIn('Worker feedback snapshot', source)
        self.assertIn('legacy 5-batch / 100-result foreground run', source)
        self.assertIn('window.exportTxt', source)


if __name__ == "__main__":
    unittest.main()
