from pathlib import Path
import unittest


class SearchReliabilityUiTests(unittest.TestCase):
    def test_overlay_scopes_feedback_to_matching_prompt_runs(self):
        source = Path("static/search_reliability_overlay.js").read_text(encoding="utf-8")
        self.assertIn("function sameIntent", source)
        self.assertIn("intentScopedPreferences", source)
        self.assertIn("intentScopedAdaptiveContext", source)
        self.assertIn("direction_anchors: scoped.anchors", source)
        self.assertIn("conflict_names: rows.filter", source)

    def test_background_run_uses_its_audited_prompt_not_current_textarea(self):
        source = Path("static/search_reliability_overlay.js").read_text(encoding="utf-8")
        self.assertIn("function backgroundPromptForRun", source)
        self.assertIn("item?.type !== 'job_started'", source)
        self.assertIn("String(details.run_id || '') !== id", source)
        self.assertIn("bgPrompt && sameIntent(bgPrompt, prompt)", source)
        self.assertNotIn("bg?.prompt || prompt", source)

    def test_report_contains_direct_urls_observed_identity_and_timeline(self):
        source = Path("static/search_reliability_overlay.js").read_text(encoding="utf-8")
        for value in (
            "https://www.instagram.com/",
            "https://t.me/",
            "https://www.tiktok.com/@",
            "https://www.youtube.com/@",
            "https://www.facebook.com/",
            "https://x.com/",
            "ПРЯМІ ЛІНКИ ТА ФАКТИ ПЕРЕВІРКИ",
            "observed_username",
            "ХРОНОЛОГІЯ ПОШУКУ",
        ):
            self.assertIn(value, source)

    def test_report_controls_load_overlay(self):
        source = Path("static/report_controls.js").read_text(encoding="utf-8")
        self.assertIn("search_reliability_overlay.js?v=1", source)
        self.assertIn("TXT + перевірки", source)

    def test_worker_entry_installs_hardening(self):
        source = Path("worker_entry.py").read_text(encoding="utf-8")
        self.assertIn("install_search_worker_hardening", source)
        self.assertIn("install_search_worker_hardening(search_worker)", source)

    def test_browser_image_copies_hardening_module(self):
        dockerfile = Path("Dockerfile.browser-eye").read_text(encoding="utf-8")
        ready = Path("browser_eye_ready.py").read_text(encoding="utf-8")
        self.assertIn("COPY browser_eye_hardening.py ./", dockerfile)
        self.assertIn("install_browser_eye_hardening", ready)


if __name__ == "__main__":
    unittest.main()
