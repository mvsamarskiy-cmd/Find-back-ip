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

    def test_timeout_and_port_can_be_overridden(self):
        with patch.dict(
            os.environ,
            {"PORT": "9000", "GUNICORN_TIMEOUT": "240"},
            clear=True,
        ):
            config = load_gunicorn_config()

        self.assertEqual(config.bind, "0.0.0.0:9000")
        self.assertEqual(config.timeout, 240)

    def test_railway_uses_the_checked_in_gunicorn_config(self):
        railway = json.loads((ROOT / "railway.json").read_text())

        self.assertEqual(
            railway["deploy"]["startCommand"],
            "gunicorn app:app --config gunicorn.conf.py",
        )
        self.assertEqual(railway["deploy"]["healthcheckPath"], "/health")

    def test_procfile_does_not_duplicate_runtime_settings(self):
        self.assertEqual((ROOT / "Procfile").read_text().strip(), "web: gunicorn app:app")

    def test_ui_has_one_source_of_truth(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        template = (ROOT / "templates" / "index.html")

        self.assertTrue(template.is_file())
        self.assertNotIn('HTML = """', app_source)
