from pathlib import Path
import unittest

from telegram_bootstrap import RELEASE_MARKER, app


class UiCleanupR8Tests(unittest.TestCase):
    def test_cleanup_layer_loads_after_live_and_brand_wrappers(self):
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('/static/feed_navigation.js?v=3', body)
        self.assertIn('/static/durable_live_events.js?v=1', body)
        self.assertIn('/static/ui_cleanup_r8.js?v=1', body)
        self.assertLess(body.index('/static/feed_navigation.js?v=3'), body.index('/static/ui_cleanup_r8.js?v=1'))
        self.assertLess(body.index('/static/durable_live_events.js?v=1'), body.index('/static/ui_cleanup_r8.js?v=1'))
        # This test protects the R8 layer, not one historical release string.
        self.assertTrue(RELEASE_MARKER.startswith('v8.'))

    def test_large_telemetry_is_collapsed_by_default_but_not_deleted(self):
        source = Path('static/ui_cleanup_r8.js').read_text(encoding='utf-8')
        self.assertIn('largeSearchCompact', source)
        self.assertIn('nm-telemetry-collapsed', source)
        self.assertIn('largeSearchTelemetry', source)
        self.assertIn('Деталі', source)
        self.assertIn('Сховати деталі', source)
        self.assertIn('MutationObserver', source)
        self.assertNotIn('removeChild', source)

    def test_report_preview_has_three_real_close_paths(self):
        source = Path('static/ui_cleanup_r8.js').read_text(encoding='utf-8')
        self.assertIn('Переглянути звіт', source)
        self.assertIn('data-report-close', source)
        self.assertIn('>×</button>', source)
        self.assertIn("event.key === 'Escape'", source)
        self.assertIn('event.target === modal', source)
        self.assertIn('window.clientReportTxt', source)

    def test_diagnostics_describe_compact_ui_and_closable_preview(self):
        diagnostics = app.test_client().get('/api/verification/diagnostics').get_json()
        ui = diagnostics['background_search_ui']
        self.assertEqual(ui['telemetry_default'], 'compact')
        self.assertTrue(ui['technical_details_toggle'])
        self.assertTrue(ui['report_preview_closable'])


if __name__ == '__main__':
    unittest.main()
