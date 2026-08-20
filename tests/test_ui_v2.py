from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UI_JS = (ROOT / "static" / "ui_cleanup_r8.js").read_text(encoding="utf-8")
UI_CSS = (ROOT / "static" / "ui_v2.css").read_text(encoding="utf-8")


class UiV2Tests(unittest.TestCase):
    def test_modern_shell_is_layered_without_backend_truth_rewrite(self):
        self.assertIn("nm-ui-v2", UI_JS)
        self.assertIn("/static/ui_v2.css?v=1", UI_JS)
        self.assertIn("Знайди назву, домен і нікнейми", UI_JS)
        self.assertIn("AI → перевірка → докази → рейтинг", UI_JS)
        self.assertNotIn("claimable =", UI_JS)
        self.assertNotIn("status = 'claimable'", UI_JS)

    def test_truth_legend_keeps_paid_promising_and_strict_free_distinct(self):
        self.assertIn("вільне — підтверджено", UI_JS)
        self.assertIn("можна купити", UI_JS)
        self.assertIn("перспективне", UI_JS)
        self.assertIn("зайняте", UI_JS)
        self.assertIn(".nm-truth-legend .strict i", UI_CSS)
        self.assertIn(".nm-truth-legend .paid i", UI_CSS)
        self.assertIn(".nm-truth-legend .promising i", UI_CSS)
        self.assertIn(".nm-truth-legend .conflict i", UI_CSS)

    def test_ui_v2_has_desktop_mobile_and_reduced_motion_contracts(self):
        self.assertIn("grid-template-columns: repeat(2, minmax(0,1fr))", UI_CSS)
        self.assertIn("@media (max-width: 640px)", UI_CSS)
        self.assertIn("@media (prefers-reduced-motion: reduce)", UI_CSS)
        self.assertIn("overflow-x: auto", UI_CSS)
        self.assertIn("min-height: 48px", UI_CSS)

    def test_search_state_observer_is_bounded_to_button_attributes(self):
        self.assertIn("attributeFilter: ['disabled']", UI_JS)
        self.assertNotIn("searchStateObserver.observe(document.body", UI_JS)
        self.assertIn("document.body.classList.toggle('nm-search-active', active)", UI_JS)

    def test_session_copy_matches_current_durable_behavior(self):
        self.assertIn("Сесія, результати та відгуки зберігаються автоматично", UI_JS)
        self.assertNotIn("Серверне збереження та email будуть окремим наступним етапом", UI_JS)


if __name__ == "__main__":
    unittest.main()
