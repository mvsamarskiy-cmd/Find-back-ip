from pathlib import Path
import unittest

from telegram_bootstrap import app


class AuditReportUiTests(unittest.TestCase):
    def test_audit_report_loads_after_background_search_before_feed_navigation(self):
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('/static/audit_report.js', body)
        self.assertLess(body.index('/static/background_search.js'), body.index('/static/audit_report.js'))
        self.assertLess(body.index('/static/audit_report.js'), body.index('/static/feed_navigation.js'))

    def test_report_fetches_live_jobs_and_preserves_historical_resource_evidence(self):
        source = Path("static/audit_report.js").read_text(encoding="utf-8")
        self.assertIn("search-jobs?limit=100", source)
        self.assertIn("resourcesForRow(row)", source)
        self.assertIn("Current checkboxes describe the current UI state only", source)
        self.assertNotIn("for (const resource of current?.resources", source)

    def test_report_correlates_feedback_with_worker_ack_and_next_candidates(self):
        source = Path("static/audit_report.js").read_text(encoding="utf-8")
        self.assertIn("FEEDBACK IMPACT AUDIT", source)
        self.assertIn("firstWorkerAckAfter", source)
        self.assertIn("worker reaction: ACK", source)
        self.assertIn("names after ACK", source)
        self.assertIn("not proof that the feedback caused", source)

    def test_report_separates_background_mirrors_from_foreground_runs(self):
        source = Path("static/audit_report.js").read_text(encoding="utf-8")
        self.assertIn("BACKGROUND JOBS — LIVE SERVER STATE", source)
        self.assertIn("FOREGROUND RUNS", source)
        self.assertIn("background_job_id", source)
        self.assertIn("UNFINISHED_METADATA", source)
        self.assertIn("NO_NEW_CANDIDATES", source)

    def test_report_has_timing_batch_and_resource_aggregates(self):
        source = Path("static/audit_report.js").read_text(encoding="utf-8")
        self.assertIn("Тривалість сесії до звіту", source)
        self.assertIn("hard-collision rate", source)
        self.assertIn("BATCHES", source)
        self.assertIn("RESOURCE STATUS AGGREGATE", source)
        self.assertIn("first candidate", source)


if __name__ == "__main__":
    unittest.main()
