import importlib.util
import json
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_gunicorn_config():
    spec = importlib.util.spec_from_file_location(
        "gunicorn_config", ROOT / "gunicorn.conf.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProductionConfigTests(TestCase):
    def test_default_worker_timeout_allows_slow_ai_requests(self):
        with patch.dict(os.environ, {}, clear=True):
            config = load_gunicorn_config()

        self.assertEqual(config.bind, "0.0.0.0:8080")
        self.assertGreaterEqual(config.timeout, 120)

    def test_default_web_runtime_is_threaded_for_long_streams(self):
        with patch.dict(os.environ, {}, clear=True):
            config = load_gunicorn_config()

        self.assertEqual(config.workers, 1)
        self.assertEqual(config.worker_class, "gthread")
        self.assertGreaterEqual(config.threads, 4)

    def test_timeout_port_threads_and_workers_can_be_overridden(self):
        with patch.dict(
            os.environ,
            {
                "PORT": "9000",
                "GUNICORN_TIMEOUT": "240",
                "GUNICORN_THREADS": "8",
                "WEB_CONCURRENCY": "2",
            },
            clear=True,
        ):
            config = load_gunicorn_config()

        self.assertEqual(config.bind, "0.0.0.0:9000")
        self.assertEqual(config.timeout, 240)
        self.assertEqual(config.threads, 8)
        self.assertEqual(config.workers, 2)

    def test_invalid_runtime_integers_fall_back_or_are_bounded(self):
        with patch.dict(
            os.environ,
            {
                "GUNICORN_TIMEOUT": "bad",
                "GUNICORN_THREADS": "999",
                "WEB_CONCURRENCY": "0",
            },
            clear=True,
        ):
            config = load_gunicorn_config()

        self.assertEqual(config.timeout, 180)
        self.assertEqual(config.threads, 16)
        self.assertEqual(config.workers, 1)

    def test_railway_uses_the_checked_in_gunicorn_config(self):
        railway = json.loads((ROOT / "railway.json").read_text())

        self.assertEqual(
            railway["deploy"]["startCommand"],
            "gunicorn private_global_bootstrap:app --config gunicorn.conf.py",
        )
        self.assertEqual(railway["deploy"]["healthcheckPath"], "/health")

    def test_procfile_does_not_duplicate_runtime_settings(self):
        self.assertEqual(
            (ROOT / "Procfile").read_text().strip(),
            "web: gunicorn private_global_bootstrap:app",
        )

    def test_browser_eye_image_contains_all_imported_runtime_modules(self):
        dockerfile = (ROOT / "Dockerfile.browser-eye").read_text(encoding="utf-8")
        ready = (ROOT / "browser_eye_ready.py").read_text(encoding="utf-8")

        self.assertIn("from browser_eye_global_search import install_browser_global_search", ready)
        self.assertIn("COPY browser_eye_global_search.py ./", dockerfile)
        self.assertIn("COPY browser_eye_hardening.py ./", dockerfile)
        self.assertIn("COPY browser_eye_service.py ./", dockerfile)
        self.assertIn("COPY browser_eye_ready.py ./", dockerfile)

    def test_bootstrap_installs_telegram_integration_before_importing_app(self):
        source = (ROOT / "telegram_bootstrap.py").read_text(encoding="utf-8")
        self.assertLess(source.index("install()"), source.index("from app import app"))

    def test_private_bootstrap_layers_universal_search_over_canonical_bootstrap(self):
        source = (ROOT / "private_global_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("from telegram_bootstrap import app", source)
        self.assertIn("from universal_search_multi import search_universal", source)
        self.assertIn("global_searcher=search_universal", source)

    def test_ui_has_one_source_of_truth(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        template = (ROOT / "templates" / "index.html")

        self.assertTrue(template.is_file())
        self.assertNotIn('HTML = """', app_source)


if __name__ == "__main__":
    import unittest
    unittest.main()
