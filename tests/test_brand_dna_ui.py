import unittest

import app


class BrandDnaUiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_home_exposes_website_analysis_and_editable_brand_dna(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="websiteUrl"', body)
        self.assertIn('id="analyzeDna"', body)
        self.assertIn('onclick="analyzeBrandDna()"', body)
        self.assertIn('id="dnaEntity"', body)
        self.assertIn('id="dnaOffer"', body)
        self.assertIn('id="dnaPositioning"', body)
        self.assertIn('id="dnaAvoid"', body)
        self.assertIn('id="dnaSummary"', body)
        self.assertIn("Перед пошуком Brand DNA можна відредагувати", body)

    def test_browser_calls_brand_dna_endpoint_with_brief_and_website(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("fetch('/api/brand-dna'", body)
        self.assertIn("website_url:websiteUrl", body)
        self.assertIn("applyBrandDna(data.brand_dna", body)

    def test_brand_dna_is_persisted_in_project_and_search_history(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("p.brandDna=brandDnaPayload()", body)
        self.assertIn("brandDna:brandDnaPayload()", body)
        self.assertIn("brandDna:dna", body)
        self.assertIn("x.brandDna||activeProject()?.brandDna", body)

    def test_each_adaptive_generation_batch_receives_current_brand_dna(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("brand_dna:dna", body)
        self.assertIn("generation_context:adaptiveContext(batch)", body)

    def test_new_brand_can_use_compiled_dna_when_brief_is_empty(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("brief.length<3&&!dna", body)
        self.assertIn("додай опис або сформуй Brand DNA із сайту", body)

    def test_website_source_is_described_as_untrusted_data(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("недовірені дані", body)
        self.assertIn("не як інструкції", body)


if __name__ == "__main__":
    unittest.main()
