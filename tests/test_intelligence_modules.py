import unittest

from intelligence_modules import (
    build_module_search_plan,
    classify_research_module,
    intelligence_module_capabilities,
    source_affinity,
)


class IntelligenceModuleTests(unittest.TestCase):
    def test_company_person_news_and_technical_routes_are_distinct(self):
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

    def test_single_current_word_does_not_turn_weather_into_news(self):
        self.assertEqual(
            classify_research_module("weather today in Warsaw")["route"],
            "general_web",
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

    def test_preferred_hosts_are_ranking_only(self):
        self.assertGreater(source_affinity("technical", "docs.python.org"), 0)
        self.assertGreater(source_affinity("news", "www.reuters.com"), 0)
        self.assertEqual(source_affinity("person", "random.example"), 0)

    def test_capabilities_publish_truth_semantics(self):
        caps = intelligence_module_capabilities()
        self.assertEqual(set(caps), {"technical", "news", "company", "person"})
        for payload in caps.values():
            self.assertTrue(payload["preferred_host_ranking_only"])
            self.assertEqual(
                payload["truth_semantics"],
                "retrieval_evidence_not_verified_fact",
            )


if __name__ == "__main__":
    unittest.main()
