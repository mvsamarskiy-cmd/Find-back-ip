import unittest

from universal_search import classify_search_route


class MoneyRouterV2Tests(unittest.TestCase):
    def test_broad_money_opportunity_query_uses_opportunity_lane(self):
        decision = classify_search_route("Знайди всі матеріальні можливості де є гроші")
        self.assertEqual(decision["route"], "opportunity")
        self.assertEqual(decision["routed_category"], "material")
        self.assertEqual(decision["reason"], "high_confidence_opportunity_intent")

    def test_liquidation_asset_search_uses_opportunity_lane(self):
        decision = classify_search_route("Знайди ліквідаційне обладнання для виробництва у Польщі")
        self.assertEqual(decision["route"], "opportunity")
        self.assertEqual(decision["routed_category"], "material")

    def test_investment_banking_definition_remains_general(self):
        decision = classify_search_route("What is investment banking?")
        self.assertEqual(decision["route"], "general_web")


if __name__ == "__main__":
    unittest.main()
