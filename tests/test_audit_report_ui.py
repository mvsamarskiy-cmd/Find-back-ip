from pathlib import Path
import unittest

from telegram_bootstrap import app


class AuditReportUiTests(unittest.TestCase):
    def test_report_v4_loads_after_background_search_with_controls(self):
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('/static/audit_report.js?v=4', body)
        self.assertIn('/static/report_controls.js?v=4', body)
        self.assertLess(body.index('/static/background_search.js'), body.index('/static/audit_report.js?v=4'))
        self.assertLess(body.index('/static/audit_report.js?v=4'), body.index('/static/report_controls.js?v=4'))
        self.assertLess(body.index('/static/report_controls.js?v=4'), body.index('/static/feed_navigation.js'))

    def test_default_report_is_compact_categorized_and_single_clock(self):
        source = Path("static/audit_report.js").read_text(encoding="utf-8")
        self.assertIn("NameMachine SESSION REPORT v4", source)
        self.assertIn("1. ПІДСУМОК", source)
        self.assertIn("2. ЩО ШУКАЛИ", source)
        self.assertIn("3. ВИБРАНЕ КОРИСТУВАЧЕМ", source)
        self.assertIn("6. ДІЇ КОРИСТУВАЧА І РЕАКЦІЯ WORKER", source)
        self.assertIn("9. ДАНІ ДЛЯ ПРОДОВЖЕННЯ РОБОТИ", source)
        self.assertIn("Загальний час від початку сесії", source)
        self.assertIn("function tplus", source)
        self.assertNotIn("duration=", source)

    def test_default_report_does_not_dump_full_candidate_ledger(self):
        source = Path("static/audit_report.js").read_text(encoding="utf-8")
        compact_start = source.index("function buildCompactReport")
        technical_start = source.index("function buildTechnicalAudit")
        compact = source[compact_start:technical_start]
        self.assertNotIn("FULL CANDIDATE LEDGER", compact)
        self.assertIn("FULL CANDIDATE LEDGER", source[technical_start:])
        self.assertIn("source=${payload?.source", source)
        self.assertIn("confidence=${payload?.confidence", source)

    def test_feedback_events_use_session_time_and_worker_ack(self):
        source = Path("static/audit_report.js").read_text(encoding="utf-8")
        self.assertIn("firstWorkerAckAfter", source)
        self.assertIn("worker прочитав ${tplus(ack?.at)}", source)
        self.assertIn("${tplus(event?.at)}", source)
        self.assertNotIn("ACK delay", source)

    def test_email_uses_device_mail_composer_without_server_claim(self):
        source = Path("static/audit_report.js").read_text(encoding="utf-8")
        controls = Path("static/report_controls.js").read_text(encoding="utf-8")
        self.assertIn("window.emailReport", source)
        self.assertIn("mailto:", source)
        self.assertIn("На який email підготувати звіт?", source)
        self.assertIn("Надіслати на email", controls)
        self.assertIn("Технічний аудит TXT", controls)

    def test_report_fetches_live_jobs_and_preserves_historical_resources(self):
        source = Path("static/audit_report.js").read_text(encoding="utf-8")
        self.assertIn("search-jobs?limit=100", source)
        self.assertIn("resourcesForRow(row)", source)
        self.assertIn("allHistoricalResources", source)
        self.assertNotIn("for (const resource of current?.resources", source)


if __name__ == "__main__":
    unittest.main()
