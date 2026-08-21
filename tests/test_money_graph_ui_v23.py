from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MoneyGraphUiV23Tests(unittest.TestCase):
    def test_bootstrap_loads_graph_ui_after_eligibility_before_evidence_browser(self):
        source = (ROOT / "private_global_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn('/static/money_graph_ui.js?v=1', source)
        self.assertLess(source.index("MONEY_ELIGIBILITY_UI_TAG"), source.index("MONEY_GRAPH_UI_TAG"))
        self.assertLess(source.index("MONEY_GRAPH_UI_TAG"), source.index("PRIVATE_RESEARCH_BROWSER_TAG"))

    def test_ui_exposes_graph_nodes_edges_and_candidate_truth(self):
        source = (ROOT / "static" / "money_graph_ui.js").read_text(encoding="utf-8")
        for token in ("nodes", "edges", "Graph relations", "explicit_references"):
            self.assertIn(token, source)
        self.assertIn("candidate", source)
        self.assertIn("not factual or legal identity", source)
        self.assertIn("Pairwise programme compatibility is not inferred", source)

    def test_ui_clears_stale_graph(self):
        source = (ROOT / "static" / "money_graph_ui.js").read_text(encoding="utf-8")
        self.assertIn("function clearUi()", source)
        self.assertIn("latest=null", source)
        self.assertIn("nmMoneyGraphSummary", source)
        self.assertIn(".nmg-v23", source)


if __name__ == "__main__":
    unittest.main()
