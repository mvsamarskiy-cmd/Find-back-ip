import unittest
from pathlib import Path

from telegram_bootstrap import app


class TurboSearchUiTests(unittest.TestCase):
    def test_turbo_assets_are_cache_busted(self):
        body = app.test_client().get('/').get_data(as_text=True)
        self.assertIn('/static/availability_hunter_ui.js?v=4', body)
        self.assertIn('/static/feed_navigation.js?v=3', body)
        self.assertIn('/static/entry_modes.js?v=1', body)

    def test_turbo_results_keep_all_checked_candidates_visible(self):
        source = Path('static/feed_navigation.js').read_text(encoding='utf-8')
        self.assertIn("bg.search_strategy !== 'turbo'", source)
        self.assertIn('return turboRunRows(rows);', source)
        self.assertIn('activeRows.filter(allGreen)', source)
        self.assertIn('перспективних', source)
        self.assertIn('конфліктів', source)
        self.assertIn('невідомих', source)
        self.assertNotIn('turboRunRows(rows).filter(allGreen)', source)
        self.assertNotIn('не засмічують цю стрічку', source)

    def test_turbo_ui_never_relabels_unconfirmed_as_free(self):
        source = Path('static/availability_hunter_ui.js').read_text(encoding='utf-8')
        self.assertIn('<option value="turbo">Turbo</option>', source)
        self.assertIn("strategy === 'turbo'", source)
        self.assertIn('підтверджено вільних', source)
        self.assertNotIn("status = 'claimable'", source)


if __name__ == '__main__':
    unittest.main()
