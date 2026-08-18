import unittest
from pathlib import Path

from telegram_bootstrap import app


class AvailabilityHunterUiTests(unittest.TestCase):
    def test_hunter_ui_loads_after_background_search_runtime(self):
        body = app.test_client().get('/').get_data(as_text=True)
        self.assertIn('/static/background_search.js', body)
        self.assertIn('/static/availability_hunter_ui.js?v=4', body)
        self.assertLess(
            body.index('/static/background_search.js'),
            body.index('/static/availability_hunter_ui.js?v=4'),
        )

    def test_hunter_ui_exposes_procedural_and_turbo_strategies(self):
        source = Path('static/availability_hunter_ui.js').read_text(encoding='utf-8')
        self.assertIn('hunterSearchStrategy', source)
        self.assertIn('<option value="procedural" selected>Процедурно</option>', source)
        self.assertIn('<option value="turbo">Turbo</option>', source)
        self.assertIn('search_strategy: strategy', source)
        self.assertIn("target_matches: targetMatches", source)
        self.assertIn("max_checks: maxChecks", source)
        self.assertIn("availability_hunter_started", source)

    def test_hunter_respects_selected_entry_workflow(self):
        source = Path('static/availability_hunter_ui.js').read_text(encoding='utf-8')
        self.assertIn('nameMachineSearchContext', source)
        self.assertIn('entrySearchContext', source)
        self.assertIn('entry_mode', source)
        self.assertIn('existing_brand_fixed', source)

    def test_hunter_ui_reports_matches_and_strategy_specific_progress(self):
        source = Path('static/availability_hunter_ui.js').read_text(encoding='utf-8')
        self.assertIn("runtime.matches", source)
        self.assertIn("runtime.checked", source)
        self.assertIn("_procedural_runtime", source)
        self.assertIn("plan.current_root", source)
        self.assertIn("plan.current_strategy", source)
        self.assertIn("Шукаю корінь", source)
        self.assertIn("Turbo · широке дослідження", source)


if __name__ == '__main__':
    unittest.main()
