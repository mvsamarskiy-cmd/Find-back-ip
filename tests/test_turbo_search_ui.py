import unittest
from pathlib import Path

from telegram_bootstrap import app


class TurboSearchUiTests(unittest.TestCase):
    def test_turbo_assets_are_cache_busted(self):
        body = app.test_client().get('/').get_data(as_text=True)
        self.assertIn('/static/availability_hunter_ui.js?v=3', body)
        self.assertIn('/static/feed_navigation.js?v=2', body)

    def test_turbo_primary_feed_filters_to_all_green(self):
        source = Path('static/feed_navigation.js').read_text(encoding='utf-8')
        self.assertIn("bg.search_strategy !== 'turbo'", source)
        self.assertIn('turboRunRows(rows).filter(allGreen)', source)
        self.assertIn('Turbo ще не знайшов жодного підтверджено вільного результату', source)
        self.assertIn('відсіяно', source)
        self.assertIn('rejected rows remain durable', source)

    def test_turbo_ui_never_relabels_unconfirmed_as_free(self):
        source = Path('static/availability_hunter_ui.js').read_text(encoding='utf-8')
        self.assertIn('<option value="turbo">Turbo</option>', source)
        self.assertIn("strategy === 'turbo'", source)
        self.assertIn('підтверджено вільних', source)
        self.assertNotIn("status = 'claimable'", source)


if __name__ == '__main__':
    unittest.main()
