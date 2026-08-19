from pathlib import Path
import unittest

from telegram_bootstrap import RELEASE_MARKER, app


class VariantExpansionUiTests(unittest.TestCase):
    def setUp(self):
        self.source = Path('static/variant_expansion_ui.js').read_text(encoding='utf-8')
        self.sync_source = Path('static/variant_expansion_sync.js').read_text(encoding='utf-8')

    def test_ui_and_sync_are_loaded_in_order(self):
        body = app.test_client().get('/').get_data(as_text=True)
        cleanup = '/static/ui_cleanup_r8.js?v=2'
        variant = '/static/variant_expansion_ui.js?v=1'
        sync = '/static/variant_expansion_sync.js?v=1'
        for tag in (cleanup, variant, sync):
            self.assertIn(tag, body)
        self.assertLess(body.index(cleanup), body.index(variant))
        self.assertLess(body.index(variant), body.index(sync))
        self.assertTrue(RELEASE_MARKER.startswith('v8.'))

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
        self.assertIn("text: '🔴 Зайнято'", self.source)
        self.assertIn("text: '⚪ Не вдалося підтвердити'", self.source)

    def test_primary_feed_is_not_repurposed_for_platform_variants(self):
        self.assertNotIn('current.results.push', self.source)
        self.assertNotIn('current.results.unshift', self.source)
        self.assertIn('expansionState', self.source)

    def test_expansion_requires_explicit_option_before_generation(self):
        self.assertIn('hasExplicitChoice', self.source)
        self.assertIn('Обери хоча б один тип варіації.', self.source)

    def test_modal_has_all_close_paths(self):
        self.assertIn("modal.querySelector('[data-variant-close]').addEventListener('click', closeModal)", self.source)
        self.assertIn('if (event.target === modal) closeModal();', self.source)
        self.assertIn("event.key === 'Escape'", self.source)

    def test_sync_uses_separate_authenticated_session_endpoint(self):
        self.assertIn('/variant-expansions/', self.sync_source)
        self.assertIn('X-NameMachine-Session-Token', self.sync_source)
        self.assertNotIn('/candidates/batch', self.sync_source)

    def test_diagnostics_expose_ui_and_durable_sync(self):
        diagnostics = app.test_client().get('/api/verification/diagnostics').get_json()
        ui = diagnostics['background_search_ui']
        self.assertTrue(ui['variant_expansion_ui'])
        self.assertTrue(ui['variant_expansion_durable_sync'])


if __name__ == '__main__':
    unittest.main()
