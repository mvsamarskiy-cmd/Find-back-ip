import unittest
from pathlib import Path

from private_global_bootstrap import app


ROOT = Path(__file__).resolve().parents[1]


class PrivateMobileResultQualityUiTests(unittest.TestCase):
    def test_explainer_loads_after_report_layers(self):
        body = app.test_client().get('/').get_data(as_text=True)
        report = '/static/private_money_report.js?v=1'
        identity = '/static/private_report_run_identity.js?v=2'
        explainer = '/static/private_result_explainer.js?v=1'
        for tag in (report, identity, explainer):
            self.assertIn(tag, body)
        self.assertLess(body.index(report), body.index(identity))
        self.assertLess(body.index(identity), body.index(explainer))

    def test_run_identity_does_not_reparse_large_private_json(self):
        source = (ROOT / 'static' / 'private_report_run_identity.js').read_text(encoding='utf-8')
        self.assertIn("url.includes('/api/private-mode/search')", source)
        self.assertNotIn('response.clone().json()', source)
        self.assertIn("run.status = 'completed'", source)

    def test_explainer_has_human_readable_card_sections_without_extra_fetch(self):
        source = (ROOT / 'static' / 'private_result_explainer.js').read_text(encoding='utf-8')
        self.assertIn("'Про що це'", source)
        self.assertIn("'Чому тут'", source)
        self.assertIn("'Що можна отримати'", source)
        self.assertIn("'Що не підтверджено'", source)
        self.assertIn('__nmPrivateMoneyReportSnapshot', source)
        self.assertNotIn("fetch('/api/private-mode/search", source)
        self.assertNotIn('response.clone()', source)


if __name__ == '__main__':
    unittest.main()
