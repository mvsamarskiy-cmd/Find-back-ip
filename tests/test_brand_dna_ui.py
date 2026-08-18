import unittest

import app


class BrandDnaUiTests(unittest.TestCase):
    def setUp(self):
        self.body = app.app.test_client().get("/").get_data(as_text=True)

    def test_primary_ui_is_one_prompt_instead_of_brand_dna_form(self):
        self.assertIn('id="prompt"', self.body)
        self.assertIn("Опиши, що вже маєш і що хочеш знайти", self.body)
        self.assertNotIn('id="dnaEntity"', self.body)
        self.assertNotIn('id="dnaOffer"', self.body)
        self.assertNotIn('id="dnaPositioning"', self.body)
        self.assertNotIn('id="dnaAvoid"', self.body)
        self.assertNotIn('id="websiteUrl"', self.body)

    def test_brand_dna_endpoint_is_not_removed_from_backend(self):
        rules = {rule.rule for rule in app.app.url_map.iter_rules()}
        self.assertIn("/api/brand-dna", rules)

    def test_frontend_keeps_backend_contract_simple_until_intent_compiler_release(self):
        self.assertIn("brand_dna:null", self.body)
        self.assertIn("search_context:{mode:'new_brand'", self.body)
        self.assertIn("generation_context:adaptiveContext(globalBatch)", self.body)


if __name__ == "__main__":
    unittest.main()
