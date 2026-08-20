from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "static" / "ui_v3_clarity.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "ui_v3_clarity.css").read_text(encoding="utf-8")


class UiV3ClarityTests(unittest.TestCase):
    def test_old_generic_mode_no_longer_silently_disables_verification(self):
        self.assertIn("mode === 'generic_name'", UI)
        self.assertIn("applyLegacyMode('brand')", UI)
        self.assertIn("current.uiIdeaOnly !== true", UI)
        self.assertIn("Лише ідеї, без перевірки", UI)

    def test_main_workflow_has_two_clear_choices(self):
        self.assertIn('data-nm-flow="brand"', UI)
        self.assertIn('data-nm-flow="identity"', UI)
        self.assertIn('Створити назву', UI)
        self.assertIn('Перевірити назву', UI)
        self.assertIn('#entryModePanel{display:none!important}', CSS)

    def test_results_open_on_ranked_feed_instead_of_empty_green_gate(self):
        self.assertIn("label(feed, 'Результати')", UI)
        self.assertIn("label(recommended, 'Підтверджені')", UI)
        self.assertIn("switchTab('feed')", UI)
        self.assertIn('підтверджено вільних', UI)
        self.assertIn('без явного конфлікту', UI)

    def test_mobile_cards_compact_platforms_actions_and_brand_details(self):
        self.assertIn("wrap.className = 'checks'", UI)
        self.assertIn("more.className = 'nm-card-more'", UI)
        self.assertIn("details.className = 'nm-brand-details'", UI)
        self.assertIn('.nm-ui-v3 .checks{display:grid', CSS)
        self.assertIn('.nm-card-more-menu', CSS)
        self.assertIn('.nm-brand-details>summary', CSS)

    def test_advanced_hunter_is_collapsed_but_available(self):
        self.assertIn("details.className = 'nm-deep-search'", UI)
        self.assertIn('Глибокий пошук вільних', UI)
        self.assertIn('.nm-deep-search>summary', CSS)

    def test_truth_semantics_are_not_rewritten(self):
        self.assertNotIn("status = 'claimable'", UI)
        self.assertNotIn("status='claimable'", UI)
        self.assertIn('Зелений з’являється лише після авторитетного підтвердження', UI)

    def test_dynamic_result_observer_is_scoped_and_idempotent(self):
        self.assertIn("observer.observe(grid, { childList: true, subtree: true })", UI)
        self.assertNotIn("observe(document.body", UI)
        self.assertIn("summary.innerHTML !== nextHtml", UI)
        self.assertIn("head.innerHTML !== nextHtml", UI)


if __name__ == '__main__':
    unittest.main()
