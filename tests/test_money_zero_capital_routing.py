import unittest

from money_query_planner import build_money_search_plan, compile_money_profile
from opportunity_search import infer_query_category
from universal_search import classify_search_route


class ZeroCapitalMoneyRoutingTests(unittest.TestCase):
    def test_ukrainian_zero_zloty_business_routes_to_money(self):
        query = "Знайди бізнес за 0 злотих"
        self.assertEqual(infer_query_category(query), "material")
        decision = classify_search_route(query, category="all")
        self.assertEqual(decision["route"], "opportunity")
        self.assertEqual(decision["routed_category"], "material")

    def test_zero_capital_business_phrases_route_across_supported_languages(self):
        examples = (
            "Знайди бізнес без вкладень",
            "Знайди бізнес з нуля",
            "Znajdź biznes za 0 zł",
            "Znajdź biznes bez kapitału",
            "Find a business with zero capital",
            "Find a business without investment",
        )
        for query in examples:
            with self.subTest(query=query):
                self.assertEqual(infer_query_category(query), "material")
                self.assertEqual(classify_search_route(query)["route"], "opportunity")

    def test_plain_business_research_is_not_forced_into_money(self):
        self.assertEqual(infer_query_category("Explain how a restaurant business works"), "all")

    def test_zero_zloty_becomes_explicit_capital_constraint_without_country_inference(self):
        profile = compile_money_profile("Знайди бізнес за 0 злотих", country="EU")
        self.assertTrue(profile["money_intent"])
        self.assertEqual(profile["country"], "EU")
        self.assertEqual(profile["capital_constraint"]["maximum_upfront_cash"], 0)
        self.assertEqual(profile["capital_constraint"]["currency"], "PLN")
        self.assertFalse(profile["capital_constraint"]["candidate_requirement_verified"])

    def test_zero_capital_planner_prioritizes_business_mechanisms(self):
        query = "Знайди бізнес за 0 злотих"
        plan = build_money_search_plan(query, country="EU")
        lanes = plan["lanes"]
        self.assertEqual(lanes[0]["lane"], "exact")
        self.assertEqual(lanes[0]["query"], query)
        self.assertEqual(sum(1 for lane in lanes if lane["query"] == query), 1)
        families = [lane["family"] for lane in lanes[1:]]
        self.assertEqual(families[:4], ["assets", "local", "off_market", "revenue"])
        self.assertIn("funding", families)
        self.assertIn("capital", families)
        self.assertTrue(all(lane["lane"] == "zero_capital_expansion" for lane in lanes[1:]))
        self.assertLessEqual(len(lanes), 7)

    def test_zero_capital_is_search_constraint_not_candidate_fact(self):
        profile = compile_money_profile("Znajdź biznes bez kapitału", country="PL")
        constraint = profile["capital_constraint"]
        self.assertEqual(constraint["source"], "explicit_user_constraint")
        self.assertFalse(constraint["candidate_requirement_verified"])


if __name__ == "__main__":
    unittest.main()
