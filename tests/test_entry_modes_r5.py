import types
import unittest
from pathlib import Path
from unittest.mock import patch

import entry_mode_backend
import generic_naming_api
from telegram_bootstrap import app


class EntryModeBackendTests(unittest.TestCase):
    def test_mode_marker_is_narrow_and_strippable(self):
        marker = entry_mode_backend.mode_lock_marker("existing_brand_fixed")
        self.assertEqual(marker, "[[nm-mode-lock:existing_brand_fixed]]")
        self.assertEqual(
            entry_mode_backend.strip_mode_lock(marker + " keep this guidance"),
            "keep this guidance",
        )
        with self.assertRaises(ValueError):
            entry_mode_backend.mode_lock_marker("turbo")

    def test_explicit_identity_mode_overrides_ai_inference(self):
        fake = types.SimpleNamespace()

        def base(_brief, _resources, _search_context):
            return (
                "AI interpreted brief",
                {"mode": "new_brand", "brand_name": "", "guidance": "AI guidance"},
                {
                    "task": "new_brand_naming",
                    "search_mode": "new_brand",
                    "brand_name": "",
                    "brand_lock": "new",
                    "naming_roots": ["bottle", "glass"],
                },
            )

        fake.apply_prompt_intelligence = base
        previous = entry_mode_backend._INSTALLED
        try:
            entry_mode_backend._INSTALLED = False
            entry_mode_backend.install_entry_mode_intelligence(fake)
            brief, context, intelligence = fake.apply_prompt_intelligence(
                "find usernames",
                ["telegram"],
                {
                    "mode": "existing_brand_fixed",
                    "brand_name": "Botella",
                    "guidance": "[[nm-mode-lock:existing_brand_fixed]] only close variants",
                },
            )
        finally:
            entry_mode_backend._INSTALLED = previous

        self.assertEqual(brief, "AI interpreted brief")
        self.assertEqual(context["mode"], "existing_brand_fixed")
        self.assertEqual(context["brand_name"], "Botella")
        self.assertNotIn("nm-mode-lock", context["guidance"])
        self.assertEqual(intelligence["task"], "existing_identity_search")
        self.assertEqual(intelligence["brand_lock"], "fixed")
        self.assertEqual(intelligence["naming_roots"], ["bottle", "glass"])

    def test_existing_brand_lock_requires_brand_name(self):
        fake = types.SimpleNamespace(
            apply_prompt_intelligence=lambda brief, resources, search_context: (
                brief,
                {"mode": "new_brand", "brand_name": "", "guidance": ""},
                {},
            )
        )
        previous = entry_mode_backend._INSTALLED
        try:
            entry_mode_backend._INSTALLED = False
            entry_mode_backend.install_entry_mode_intelligence(fake)
            with self.assertRaisesRegex(ValueError, "requires a brand name"):
                fake.apply_prompt_intelligence(
                    "find handles",
                    ["telegram"],
                    {
                        "mode": "existing_brand_fixed",
                        "brand_name": "",
                        "guidance": "[[nm-mode-lock:existing_brand_fixed]]",
                    },
                )
        finally:
            entry_mode_backend._INSTALLED = previous


class GenericNamingApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch("generic_naming_api.generate_generic_names")
    def test_generic_naming_does_not_require_resources_or_verifier(self, generate):
        generate.return_value = [{
            "name": "Vesselum",
            "family": "root_blend",
            "reason": "fixture",
            "pronunciation": "ves-se-lum",
            "language_risks": [],
            "checked": False,
            "product_mode": "generic_name",
        }]
        response = self.client.post("/api/generic-names", json={
            "brief": "придумай ім'я для бота",
            "count": 1,
            "resources": [],
        })
        self.assertEqual(response.status_code, 200)
        rows = response.get_json()
        self.assertEqual(rows[0]["product_mode"], "generic_name")
        self.assertFalse(rows[0]["checked"])
        self.assertNotIn("availability", rows[0])
        generate.assert_called_once()

    def test_generic_naming_validates_brief_before_ai(self):
        response = self.client.post("/api/generic-names", json={"brief": "x", "count": 10})
        self.assertEqual(response.status_code, 400)


class EntryModeUiTests(unittest.TestCase):
    def test_four_product_entry_modes_are_visible(self):
        source = Path("static/entry_modes.js").read_text(encoding="utf-8")
        self.assertIn("Створити бренд", source)
        self.assertIn("Нікнейми / домени", source)
        self.assertIn("Придумати назву", source)
        self.assertIn("Інше", source)
        self.assertIn("existingBrandName", source)
        self.assertIn("/api/generic-names", source)
        self.assertIn("Перевірки доступності не виконуються", source)

    def test_generic_mode_hides_verification_controls_but_keeps_feedback(self):
        source = Path("static/entry_modes.js").read_text(encoding="utf-8")
        self.assertIn("body.nm-mode-generic_name .resources", source)
        self.assertIn("body.nm-mode-generic_name #largeSearchPanel", source)
        self.assertIn("class=\"like", source)
        self.assertIn("class=\"dislike", source)
        self.assertIn("direction-btn", source)
        self.assertIn("shortlist-btn", source)

    def test_entry_mode_script_loads_after_feed_and_report_modes(self):
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('/static/entry_modes.js?v=1', body)
        self.assertGreater(body.index('/static/entry_modes.js?v=1'), body.index('/static/feed_navigation.js?v=3'))
        self.assertGreater(body.index('/static/entry_modes.js?v=1'), body.index('/static/client_report_modes.js?v=1'))

    def test_streaming_uses_mode_specific_search_context(self):
        source = Path("static/streaming.js").read_text(encoding="utf-8")
        self.assertIn("nameMachineSearchContext", source)
        self.assertIn("product_mode: productMode", source)
        self.assertIn("entry_mode: mode", source)


if __name__ == "__main__":
    unittest.main()