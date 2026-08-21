import unittest

from intelligence_modules import (
    build_module_search_plan,
    classify_research_module,
    intelligence_module_capabilities,
    source_affinity,
)


class IntelligenceModuleTests(unittest.TestCase):
    def test_core_research_routes_are_distinct(self):
        self.assertEqual(
            classify_research_module("Who is the CEO of Nvidia?")["route"],
            "company",
        )
        self.assertEqual(
            classify_research_module("Who is Jensen Huang?")["route"],
            "person",
        )
        self.assertEqual(
            classify_research_module("latest Nvidia news today")["route"],
            "news",
        )
        self.assertEqual(
            classify_research_module("Python 3.14 release notes")["route"],
            "technical",
        )

    def test_product_route_requires_commerce_or_price_plus_product_context(self):
        self.assertEqual(
            classify_research_module("iPhone 17 price in Poland")["route"],
            "product",
        )
        self.assertEqual(
            classify_research_module("де купити навушники Sony найдешевше")["route"],
            "product",
        )
        self.assertEqual(
            classify_research_module("gdzie kupić MacBook Air najtaniej")["route"],
            "product",
        )
        self.assertNotEqual(
            classify_research_module("cost to start a company")["route"],
            "product",
        )
        self.assertNotEqual(
            classify_research_module("best price Bitcoin today")["route"],
            "product",
        )

    def test_local_route_needs_place_context_and_geography_or_proximity(self):
        self.assertEqual(
            classify_research_module("restaurants in Warsaw")["route"],
            "local",
        )
        self.assertEqual(
            classify_research_module("аптека поруч зі мною")["route"],
            "local",
        )
        self.assertEqual(
            classify_research_module("hotel in Krakow open now")["route"],
            "local",
        )
        self.assertEqual(
            classify_research_module("sushi near me")["route"],
            "local",
        )
        self.assertEqual(
            classify_research_module("weather today in Warsaw")["route"],
            "general_web",
        )
        self.assertNotEqual(
            classify_research_module("weather near me")["route"],
            "local",
        )
        self.assertEqual(
            classify_research_module("What is investment banking?")["route"],
            "general_web",
        )

    def test_local_and_product_beat_incidental_current_words(self):
        self.assertEqual(
            classify_research_module("best hotels in Warsaw today")["route"],
            "local",
        )
        self.assertEqual(
            classify_research_module("best price iPhone 17 today")["route"],
            "product",
        )

    def test_generic_company_word_alone_is_not_enough(self):
        self.assertEqual(
            classify_research_module("company culture")["route"],
            "general_web",
        )

    def test_query_plan_keeps_exact_user_query_first_and_is_bounded(self):
        query = "Python 3.14 release notes"
        plan = build_module_search_plan(query, "technical")
        self.assertEqual(plan[0], query)
        self.assertLessEqual(len(plan), 2)
        self.assertIn("official documentation", plan[1])

        product_plan = build_module_search_plan("iPhone 17 price", "product")
        self.assertEqual(product_plan[0], "iPhone 17 price")
        self.assertIn("price availability", product_plan[1])

        local_plan = build_module_search_plan("restaurants in Warsaw", "local")
        self.assertEqual(local_plan[0], "restaurants in Warsaw")
        self.assertIn("address opening hours", local_plan[1])

    def test_preferred_hosts_are_ranking_only(self):
        self.assertGreater(source_affinity("technical", "docs.python.org"), 0)
        self.assertGreater(source_affinity("news", "www.reuters.com"), 0)
        self.assertGreater(source_affinity("product", "www.ceneo.pl"), 0)
        self.assertGreater(source_affinity("local", "www.tripadvisor.com"), 0)
        self.assertEqual(source_affinity("person", "random.example"), 0)

    def test_capabilities_publish_truth_semantics(self):
        caps = intelligence_module_capabilities()
        self.assertEqual(
            set(caps),
            {"local", "product", "technical", "news", "company", "person"},
        )
        for payload in caps.values():
            self.assertTrue(payload["preferred_host_ranking_only"])
            self.assertEqual(
                payload["truth_semantics"],
                "retrieval_evidence_not_verified_fact",
            )


if __name__ == "__main__":
    unittest.main()
