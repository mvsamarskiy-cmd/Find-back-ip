from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MoneyOpportunityUiV21Tests(unittest.TestCase):
    def test_bootstrap_loads_money_ui_between_search_and_evidence_browser(self):
        source = (ROOT / "private_global_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn('/static/money_opportunity_ui.js?v=1', source)
        self.assertLess(source.index("UNIVERSAL_GLOBAL_MODE_TAG"), source.index("MONEY_OPPORTUNITY_UI_TAG"))
        self.assertLess(source.index("MONEY_OPPORTUNITY_UI_TAG"), source.index("PRIVATE_RESEARCH_BROWSER_TAG"))

    def test_ui_exposes_practical_evidence_fit_upside_and_freshness(self):
        source = (ROOT / "static" / "money_opportunity_ui.js").read_text(encoding="utf-8")
        for token in ("PRACTICAL", "EVIDENCE", "FIT", "UPSIDE", "FRESHNESS"):
            self.assertIn(token, source)
        self.assertIn("CURRENT CALL VERIFIED", source)
        self.assertIn("Оригінальні джерела", source)
        self.assertIn("direct_verification", source)

    def test_ui_keeps_truth_warning_and_original_links(self):
        source = (ROOT / "static" / "money_opportunity_ui.js").read_text(encoding="utf-8")
        self.assertIn("гарантована доступність", source)
        self.assertIn("source_urls", source)
        self.assertIn("a.target='_blank'", source)
        self.assertIn("noopener noreferrer", source)

    def test_ui_clears_stale_money_state_on_non_money_response(self):
        source = (ROOT / "static" / "money_opportunity_ui.js").read_text(encoding="utf-8")
        self.assertIn("function clearMoneyUi()", source)
        self.assertIn("latest=null", source)
        self.assertIn("nmMoneySummary", source)
        self.assertIn(".nmm-v21", source)
        self.assertIn("queueMicrotask(clearMoneyUi)", source)


if __name__ == "__main__":
    unittest.main()
