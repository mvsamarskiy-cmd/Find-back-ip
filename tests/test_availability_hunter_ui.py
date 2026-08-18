import unittest
from pathlib import Path

from telegram_bootstrap import app


class AvailabilityHunterUiTests(unittest.TestCase):
    def test_hunter_ui_loads_after_background_search_runtime(self):
        body = app.test_client().get('/').get_data(as_text=True)
        self.assertIn('/static/background_search.js', body)
        self.assertIn('/static/availability_hunter_ui.js?v=2', body)
        self.assertLess(
            body.index('/static/background_search.js'),
            body.index('/static/availability_hunter_ui.js?v=2'),
        )

    def test_hunter_ui_sends_result_goal_budget_and_procedural_strategy(self):
        source = Path('static/availability_hunter_ui.js').read_text(encoding='utf-8')
        self.assertIn("target_matches: targetMatches", source)
        self.assertIn("max_checks: maxChecks", source)
        self.assertIn("search_strategy: 'procedural'", source)
        self.assertIn("Пошук вільних", source)
        self.assertIn("підтверджено вільних", source)
        self.assertIn("availability_hunter_started", source)

    def test_hunter_ui_reports_matches_and_real_procedural_position(self):
        source = Path('static/availability_hunter_ui.js').read_text(encoding='utf-8')
        self.assertIn("runtime.matches", source)
        self.assertIn("runtime.checked", source)
        self.assertIn("_procedural_runtime", source)
        self.assertIn("plan.current_root", source)
        self.assertIn("plan.current_strategy", source)
        self.assertIn("Шукаю корінь", source)


if __name__ == '__main__':
    unittest.main()
