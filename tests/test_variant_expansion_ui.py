from pathlib import Path
import unittest

from telegram_bootstrap import RELEASE_MARKER, app


class VariantExpansionUiTests(unittest.TestCase):
    def setUp(self):
        self.source = Path('static/variant_expansion_ui.js').read_text(encoding='utf-8')

    def test_ui_is_loaded_after_cleanup(self):
        body = app.test_client().get('/').get_data(as_text=True)
        variant = '/static/variant_expansion_ui.js?v=1'
        cleanup = '/static/ui_cleanup_r8.js?v=1'
        self.assertIn(variant, body)
        self.assertIn(cleanup, body)
        self.assertLess(body.index(cleanup), body.index(variant))
        self.assertEqual(RELEASE_MARKER, 'v8.7-variant-expansion')

    def test_expansion_requires_explicit_choice(self):
        self.assertIn('Розширити пошук', self.source)
        self.assertIn('Чиста назва завжди перевіряється першою.', self.source)
        self.assertIn('Нічого не змінюємо без твого вибору.', self.source)
        self.assertIn('NameMachine не вигадує 123 автоматично', self.source)
        self.assertIn("row?.product_mode === 'generic_name'", self.source)

    def test_real_variant_endpoints_are_used(self):
        self.assertIn("fetch('/api/variants'", self.source)
        self.assertIn("fetch('/api/variants/check'", self.source)
        self.assertIn('MAX_CHECKS = 24', self.source)
        self.assertIn('CHECK_WORKERS = 4', self.source)

    def test_truthful_status_copy(self):
        self.assertIn("text: '🟢 Вільний'", self.source)
        self.assertIn("text: '🟣 Можна купити'", self.source)
        self.assertIn("text: '🟡 Не знайдено · не підтверджено'", self.source)

    def test_modal_has_all_close_paths(self):
        self.assertIn('variant-modal-close', self.source)
        self.assertIn("event.key === 'Escape'", self.source)
        self.assertIn('if (event.target === modal) closeModal()', self.source)
        block = self.source[self.source.index('function closeModal()'):self.source.index('function options()')]
        self.assertNotIn('running) return', block)
        self.assertIn("if (!running) activeName = ''", block)
        self.assertIn('const runName = activeName', self.source)
        self.assertIn('save(runName,', self.source)

    def test_primary_feed_is_not_repurposed_for_platform_variants(self):
        self.assertIn('current.variantExpansions', self.source)
        self.assertNotIn('current.results.push', self.source)

    def test_diagnostics_expose_ui(self):
        payload = app.test_client().get('/api/verification/diagnostics').get_json()
        self.assertTrue(payload['background_search_ui']['variant_expansion_ui'])
        self.assertEqual(payload['variant_grammar']['verification_endpoint'], '/api/variants/check')


if __name__ == '__main__':
    unittest.main()
