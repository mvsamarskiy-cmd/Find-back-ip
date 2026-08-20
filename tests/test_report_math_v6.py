import unittest
from pathlib import Path

from telegram_bootstrap import RELEASE_MARKER, app


class ReportMathV6Tests(unittest.TestCase):
    def test_math_layer_loads_before_client_report_and_overlay_after_modes(self):
        body = app.test_client().get('/').get_data(as_text=True)
        math_tag = '/static/report_math_v6.js?v=1'
        client_tag = '/static/client_report.js?v=6'
        modes_tag = '/static/client_report_modes.js?v=2'
        overlay_tag = '/static/report_math_overlay.js?v=1'
        controls_tag = '/static/report_controls.js?v=5'
        for tag in (math_tag, client_tag, modes_tag, overlay_tag, controls_tag):
            self.assertIn(tag, body)
        self.assertLess(body.index(math_tag), body.index(client_tag))
        self.assertLess(body.index(client_tag), body.index(modes_tag))
        self.assertLess(body.index(modes_tag), body.index(overlay_tag))
        self.assertLess(body.index(overlay_tag), body.index(controls_tag))
        self.assertEqual(RELEASE_MARKER, 'v8.13.0-mathematical-report')

    def test_math_report_exposes_denominators_uncertainty_and_runtime_equations(self):
        source = Path('static/report_math_v6.js').read_text(encoding='utf-8')
        self.assertIn('wilson(successes, trials', source)
        self.assertIn('95% Wilson', source)
        self.assertIn('1−e^(−n/5)', source)
        self.assertIn('0.56×structural + 0.44×linguistic', source)
        self.assertIn('0.72×I + 0.28×Opportunity + state_penalty', source)
        self.assertIn('Δ avg Final vs previous run', source)
        self.assertIn('Поточний run не завершений', source)

    def test_math_report_never_promotes_absence_or_paid_inventory_to_strict_free(self):
        source = Path('static/report_math_v6.js').read_text(encoding='utf-8')
        self.assertIn("if (statuses.every(status => status === 'claimable')) return 'claimable'", source)
        self.assertIn("if (statuses.some(status => status === 'not_found')) return 'promising'", source)
        self.assertIn("purchasable: 0.82", source)
        self.assertIn('«Вільне» дозволено лише для status=claimable', source)
        self.assertIn('ranking utility; вона не змінює істинний статус', source)

    def test_default_txt_and_email_are_wrapped_with_math_audit(self):
        source = Path('static/report_math_overlay.js').read_text(encoding='utf-8')
        self.assertIn('window.clientReportTxt = buildText', source)
        self.assertIn('window.exportClientReportTxt', source)
        self.assertIn('window.emailClientReport', source)
        self.assertIn('window.nameMachineReportMath.text', source)

    def test_diagnostics_publish_non_secret_math_contract(self):
        diagnostics = app.test_client().get('/api/verification/diagnostics').get_json()
        report = diagnostics['client_report_math']
        self.assertTrue(report['enabled'])
        self.assertEqual(report['version'], 'report-math-v6')
        self.assertEqual(report['wilson_interval'], 0.95)
        self.assertEqual(report['explicit_feedback_confidence_formula'], '1-exp(-n/5)')
        self.assertFalse(report['status_truth_rewritten_by_math'])


if __name__ == '__main__':
    unittest.main()
