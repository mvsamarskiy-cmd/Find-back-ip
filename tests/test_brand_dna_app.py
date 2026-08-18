import unittest
from unittest.mock import patch

import app


DNA = {
    "entity_type": "community commerce platform",
    "offer": "Turns community choices into limited physical products",
    "audiences": ["creators", "collectors"],
    "markets": ["Poland"],
    "languages": ["Ukrainian", "Polish"],
    "positioning": "community-led launch platform",
    "brand_traits": ["participatory", "clear"],
    "themes": ["selection", "making"],
    "naming_directions": ["short distinctive abstract names"],
    "avoid": ["generic maker terminology"],
    "keywords": ["community", "launch"],
    "summary": "A community turns ideas into real limited products.",
}


class BrandDnaApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_brand_dna_requires_brief_or_website(self):
        response = self.client.post(
            "/api/brand-dna",
            json={},
            environ_base={"REMOTE_ADDR": "198.51.100.61"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("brief or website_url", response.get_json()["error"].lower())

    @patch("app.build_brand_dna", return_value=DNA)
    @patch("app.fetch_public_website")
    def test_brand_dna_can_compile_brief_without_fetching_website(self, fetch, build):
        response = self.client.post(
            "/api/brand-dna",
            json={"brief": "Спільнота голосує за продукти"},
            environ_base={"REMOTE_ADDR": "198.51.100.62"},
        )
        self.assertEqual(response.status_code, 200)
        fetch.assert_not_called()
        build.assert_called_once_with("Спільнота голосує за продукти", None)
        self.assertEqual(response.get_json()["brand_dna"]["entity_type"], DNA["entity_type"])
        self.assertFalse(response.get_json()["source"]["website_used"])

    @patch("app.build_brand_dna", return_value=DNA)
    @patch("app.fetch_public_website", return_value={
        "url": "https://example.com/",
        "title": "Example",
        "description": "Demo",
        "text": "Public project description",
        "content_type": "text/html",
    })
    def test_brand_dna_can_use_public_website(self, fetch, build):
        response = self.client.post(
            "/api/brand-dna",
            json={"brief": "Мій бренд", "website_url": "https://example.com"},
            environ_base={"REMOTE_ADDR": "198.51.100.63"},
        )
        self.assertEqual(response.status_code, 200)
        fetch.assert_called_once_with("https://example.com")
        self.assertEqual(build.call_args.args[0], "Мій бренд")
        self.assertEqual(build.call_args.args[1]["title"], "Example")
        source = response.get_json()["source"]
        self.assertTrue(source["website_used"])
        self.assertEqual(source["website_url"], "https://example.com/")

    @patch("app.build_brand_dna")
    def test_brand_dna_blocks_private_website_before_ai(self, build):
        response = self.client.post(
            "/api/brand-dna",
            json={"website_url": "http://127.0.0.1/admin"},
            environ_base={"REMOTE_ADDR": "198.51.100.64"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()["error_type"], "WebsiteFetchError")
        build.assert_not_called()

    @patch("app.trademark_links", return_value={})
    @patch("app.check_many", return_value=[{
        "availability": {},
        "selected_resources": ["telegram"],
        "total_resources": 1,
    }])
    @patch("app.generate_ai_names", return_value=[{
        "name": "Nuvexa",
        "reason": "Причина",
        "pronunciation": "nu-VEK-sa",
        "language_risks": [],
    }])
    def test_ai_generate_passes_clean_brand_dna_to_naming(
        self, generate_ai_names, _check_many, _trademark_links
    ):
        dirty = dict(DNA)
        dirty["ignored"] = "do not pass this"
        dirty["audiences"] = [f"group {i}" for i in range(30)]
        response = self.client.post(
            "/api/ai-generate",
            json={
                "brief": "Український бренд",
                "resources": ["telegram"],
                "brand_dna": dirty,
            },
            environ_base={"REMOTE_ADDR": "198.51.100.65"},
        )
        self.assertEqual(response.status_code, 200)
        kwargs = generate_ai_names.call_args.kwargs
        self.assertIn("brand_dna", kwargs)
        self.assertNotIn("ignored", kwargs["brand_dna"])
        self.assertEqual(len(kwargs["brand_dna"]["audiences"]), 12)


if __name__ == "__main__":
    unittest.main()
