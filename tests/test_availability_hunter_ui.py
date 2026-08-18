import unittest
from pathlib import Path

from telegram_bootstrap import app


class AvailabilityHunterUiTests(unittest.TestCase):
    def test_hunter_ui_loads_after_background_search_runtime(self):
        body = app.test_client().get('/').get_data(as_text=True)
        self.assertIn('/static/background_search.js', body)
        self.assertIn('/static/availability_hunter_ui.js?v=1', body)
        self.assertLess(
            body.index('/static/background_search.js'),
            body.index('/static/availability_hunter_ui.js?v=1'),
        )

    def test_hunter_ui_sends_result_goal_and_search_budget(self):
        source = Path('static/availability_hunter_ui.js').read_text(encoding='utf-8')
        self.assertIn("target_matches: targetMatches", source)
        self.assertIn("max_checks: maxChecks", source)
        self.assertIn("Пошук вільних", source)
        self.assertIn("підтверджено вільних", source)
        self.assertIn("availability_hunter_started", source)

    def test_hunter_ui_reports_matches_separately_from_checked(self):
        source = Path('static/availability_hunter_ui.js').read_text(encoding='utf-8')
        self.assertIn("runtime.matches", source)
        self.assertIn("runtime.checked", source)
        self.assertIn("target_matches", source)
        self.assertIn("max_checks", source)


if __name__ == '__main__':
    unittest.main()
