import os
import unittest
from pathlib import Path
from unittest.mock import patch

import gunicorn.conf as gunicorn_conf


ROOT = Path(__file__).resolve().parents[1]


class ProductionConfigTests(unittest.TestCase):
    def test_railway_uses_the_checked_in_gunicorn_config(self):
        railway = (ROOT / "railway.json").read_text(encoding="utf-8")
        self.assertIn("gunicorn -c gunicorn.conf.py private_global_bootstrap:app", railway)

    def test_default_web_runtime_is_threaded_for_long_streams(self):
        self.assertEqual(gunicorn_conf.worker_class, "gthread")
        self.assertGreaterEqual(gunicorn_conf.threads, 2)
        self.assertGreaterEqual(gunicorn_conf.timeout, 30)

    def test_timeout_port_threads_and_workers_can_be_overridden(self):
        source = (ROOT / "gunicorn.conf.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("PORT", \'8080\')', source)
        self.assertIn('"WEB_CONCURRENCY"', source)
        self.assertIn('"GUNICORN_THREADS"', source)
        self.assertIn('"GUNICORN_TIMEOUT"', source)

    def test_invalid_runtime_integers_fall_back_or_are_bounded(self):
        self.assertGreaterEqual(gunicorn_conf._bounded_int("__NM_MISSING_INT__", 4, 2, 8), 2)
        with patch.dict(os.environ, {"__NM_BAD_INT__": "nope"}, clear=False):
            self.assertEqual(gunicorn_conf._bounded_int("__NM_BAD_INT__", 4, 2, 8), 4)
        with patch.dict(os.environ, {"__NM_LOW_INT__": "-9"}, clear=False):
            self.assertEqual(gunicorn_conf._bounded_int("__NM_LOW_INT__", 4, 2, 8), 2)
        with patch.dict(os.environ, {"__NM_HIGH_INT__": "99"}, clear=False):
            self.assertEqual(gunicorn_conf._bounded_int("__NM_HIGH_INT__", 4, 2, 8), 8)

    def test_default_worker_timeout_allows_slow_ai_requests(self):
        self.assertGreaterEqual(gunicorn_conf.timeout, 120)

    def test_procfile_does_not_duplicate_runtime_settings(self):
        self.assertEqual((ROOT / "Procfile").read_text().strip(), "web: gunicorn private_global_bootstrap:app")

    def test_browser_eye_image_contains_all_imported_runtime_modules(self):
        dockerfile = (ROOT / "Dockerfile.browser-eye").read_text(encoding="utf-8")
        ready = (ROOT / "browser_eye_ready.py").read_text(encoding="utf-8")
        self.assertIn("from browser_eye_global_search import install_browser_global_search", ready)
        self.assertIn("from browser_eye_tor import install_browser_tor_routes", ready)
        self.assertIn("COPY browser_eye_global_search.py ./", dockerfile)
        self.assertIn("COPY browser_eye_tor.py ./", dockerfile)
        self.assertIn("COPY browser_eye_hardening.py ./", dockerfile)
        self.assertIn("COPY browser_eye_service.py ./", dockerfile)
        self.assertIn("COPY browser_eye_ready.py ./", dockerfile)
        self.assertIn("COPY browser_eye_start.sh ./", dockerfile)
        self.assertIn("apt-get install -y --no-install-recommends tor", dockerfile)

    def test_bootstrap_installs_telegram_integration_before_importing_app(self):
        source = (ROOT / "telegram_bootstrap.py").read_text(encoding="utf-8")
        self.assertLess(source.index("install()"), source.index("from app import app"))

    def test_private_bootstrap_layers_cancellable_money_over_tor_universal_search(self):
        source = (ROOT / "private_global_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("from telegram_bootstrap import app", source)
        self.assertIn("from universal_search_tor import search_universal", source)
        self.assertIn("def search_private_universal(", source)
        self.assertIn('money_kwargs["cancel_checker"] = cancel_checker', source)
        self.assertIn('kwargs["opportunity_searcher"] = cancellable_money', source)
        self.assertIn("return search_universal(query, **kwargs)", source)
        self.assertIn("global_searcher=search_private_universal", source)

    def test_ui_has_one_source_of_truth(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        template = (ROOT / "templates" / "index.html")
        self.assertTrue(template.is_file())
        self.assertNotIn('HTML = """', app_source)


if __name__ == "__main__":
    unittest.main()
