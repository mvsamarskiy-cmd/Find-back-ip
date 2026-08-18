from pathlib import Path
import unittest

from telegram_bootstrap import app


class AuditReportUiTests(unittest.TestCase):
    def test_internal_audit_and_client_report_load_before_client_controls(self):
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('/static/audit_report.js?v=4', body)
        self.assertIn('/static/client_report.js?v=5', body)
        self.assertIn('/static/report_controls.js?v=5', body)
        self.assertLess(body.index('/static/background_search.js'), body.index('/static/audit_report.js?v=4'))
        self.assertLess(body.index('/static/audit_report.js?v=4'), body.index('/static/client_report.js?v=5'))
        self.assertLess(body.index('/static/client_report.js?v=5'), body.index('/static/report_controls.js?v=5'))
        self.assertLess(body.index('/static/report_controls.js?v=5'), body.index('/static/feed_navigation.js'))

    def test_internal_compact_report_is_categorized_and_single_clock(self):
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

    def test_internal_compact_report_does_not_dump_full_candidate_ledger(self):
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

    def test_client_email_uses_device_mail_composer_without_server_claim(self):
        client = Path("static/client_report.js").read_text(encoding="utf-8")
        controls = Path("static/report_controls.js").read_text(encoding="utf-8")
        self.assertIn("window.emailClientReport", client)
        self.assertIn("mailto:", client)
        self.assertIn("На який email підготувати звіт?", client)
        self.assertIn("Надіслати на email", controls)
        self.assertIn("Клієнтський звіт HTML", controls)
        self.assertNotIn("Технічний аудит TXT", controls)

    def test_internal_report_fetches_live_jobs_and_preserves_historical_resources(self):
        source = Path("static/audit_report.js").read_text(encoding="utf-8")
        self.assertIn("search-jobs?limit=100", source)
        self.assertIn("resourcesForRow(row)", source)
        self.assertIn("allHistoricalResources", source)
        self.assertNotIn("for (const resource of current?.resources", source)


if __name__ == "__main__":
    unittest.main()
