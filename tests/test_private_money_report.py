import unittest
from pathlib import Path

from private_global_bootstrap import app


ROOT = Path(__file__).resolve().parents[1]


class PrivateMoneyReportTests(unittest.TestCase):
    def test_bootstrap_loads_private_report_after_private_ui_layers(self):
        body = app.test_client().get('/').get_data(as_text=True)
        report = '/static/private_money_report.js?v=1'
        identity = '/static/private_report_run_identity.js?v=2'
        scroll = '/static/private_results_page_scroll_fix.js?v=1'
        self.assertIn(report, body)
        self.assertIn(identity, body)
        self.assertIn(scroll, body)
        self.assertLess(body.index(scroll), body.index(report))
        self.assertLess(body.index(report), body.index(identity))

    def test_private_report_captures_private_search_payload_not_naming_ledger(self):
        source = (ROOT / 'static' / 'private_money_report.js').read_text(encoding='utf-8')
        self.assertIn("url.includes('/api/private-mode/search')", source)
        self.assertIn('payload?.results', source)
        self.assertIn('payload?.money_records', source)
        self.assertIn('current_call_verified', source)
        self.assertIn('source_observed', source)
        self.assertIn('eligibility_state', source)
        self.assertIn('payload?.search_plan', source)
        self.assertIn('payload?.tor_retrieval', source)
        self.assertIn('payload?.truth_note', source)
        self.assertIn('MONEY / GLOBAL SEARCH REPORT', source)
        self.assertIn("document.body.classList.contains('nm-private-global')", source)

    def test_run_identity_guard_prevents_stale_payload_from_looking_fresh(self):
        source = (ROOT / 'static' / 'private_report_run_identity.js').read_text(encoding='utf-8')
        self.assertIn("url.includes('/api/private-mode/search')", source)
        self.assertIn("requested_at: nowIso()", source)
        self.assertIn("run.status = 'completed'", source)
        self.assertIn("no_search_in_this_page", source)
        self.assertIn('Старий in-memory payload навмисно не видається за новий результат', source)
        self.assertIn('Search ID:', source)
        self.assertIn('Git commit:', source)
        self.assertIn("previousFetch('/api/version'", source)
        self.assertIn('window.__nmPrivateReportRunIdentity', source)

    def test_private_report_delegates_to_public_report_outside_private_mode(self):
        source = (ROOT / 'static' / 'private_money_report.js').read_text(encoding='utf-8')
        identity = (ROOT / 'static' / 'private_report_run_identity.js').read_text(encoding='utf-8')
        self.assertIn('baseClientReportTxt', source)
        self.assertIn('baseExportTxt', source)
        self.assertIn('baseExportHtml', source)
        self.assertIn('baseEmail', source)
        self.assertIn("isPrivate() ? buildPrivateTxt()", source)
        self.assertIn(': baseExportTxt?.()', identity)
        self.assertIn(': baseExportHtml?.()', identity)
        self.assertIn("if (!isPrivate()) return baseEmail?.()", identity)

    def test_private_report_uses_opportunity_words_not_naming_summary(self):
        source = (ROOT / 'static' / 'private_money_report.js').read_text(encoding='utf-8')
        self.assertIn('Знайдено можливостей / джерел', source)
        self.assertIn('ЗНАЙДЕНІ МОЖЛИВОСТІ', source)
        self.assertNotIn('ЩО СИСТЕМА ЗРОЗУМІЛА ПРО СМАК', source)
        self.assertNotIn('ПІДТВЕРДЖЕНІ КАНДИДАТИ', source)


if __name__ == '__main__':
    unittest.main()
