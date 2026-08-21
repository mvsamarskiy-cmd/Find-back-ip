from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MoneyEligibilityUiV22Tests(unittest.TestCase):
    def test_bootstrap_loads_eligibility_ui_after_money_ui_before_evidence_browser(self):
        source = (ROOT / "private_global_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn('/static/money_eligibility_ui.js?v=1', source)
        self.assertLess(source.index("MONEY_OPPORTUNITY_UI_TAG"), source.index("MONEY_ELIGIBILITY_UI_TAG"))
        self.assertLess(source.index("MONEY_ELIGIBILITY_UI_TAG"), source.index("PRIVATE_RESEARCH_BROWSER_TAG"))

    def test_ui_exposes_four_states_and_missing_profile_facts(self):
        source = (ROOT / "static" / "money_eligibility_ui.js").read_text(encoding="utf-8")
        for token in ("eligible_candidate", "possible", "unknown", "ineligible"):
            self.assertIn(token, source)
        self.assertIn("missing_profile_fields", source)
        self.assertIn("known_fields", source)
        self.assertIn("eligibility_score", source)

    def test_ui_shows_rule_evidence_and_truth_boundary(self):
        source = (ROOT / "static" / "money_eligibility_ui.js").read_text(encoding="utf-8")
        self.assertIn("Показати всі eligibility rules", source)
        self.assertIn("Evidence:", source)
        self.assertIn("не юридичне підтвердження eligibility", source)
        self.assertIn("гарантія отримання грошей", source)

    def test_ui_clears_stale_eligibility_state(self):
        source = (ROOT / "static" / "money_eligibility_ui.js").read_text(encoding="utf-8")
        self.assertIn("function clearUi()", source)
        self.assertIn("latest=null", source)
        self.assertIn("nmEligibilitySummary", source)
        self.assertIn(".nme-v22", source)


if __name__ == "__main__":
    unittest.main()
