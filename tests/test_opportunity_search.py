import unittest

from opportunity_search import infer_query_category


class OpportunitySearchIntentTests(unittest.TestCase):
    def test_routes_ukrainian_grant_query(self):
        self.assertEqual(infer_query_category("Знайди гранти для стартапу в Польщі"), "grant")

    def test_routes_polish_business_aid_query(self):
        self.assertEqual(infer_query_category("pomoc dla firm na automatyzację"), "business_aid")

    def test_routes_challenge_query(self):
        self.assertEqual(infer_query_category("Find AI challenges with a cash prize"), "challenge")

    def test_routes_research_query(self):
        self.assertEqual(infer_query_category("Horizon research call for robotics"), "research")

    def test_unknown_query_remains_all(self):
        self.assertEqual(infer_query_category("покажи цікаві можливості"), "all")


if __name__ == "__main__":
    unittest.main()
