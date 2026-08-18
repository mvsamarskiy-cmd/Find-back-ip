from pathlib import Path
import unittest


class BackgroundWorkerEntrypointTests(unittest.TestCase):
    def test_worker_is_separate_from_canonical_web_process(self):
        procfile = Path("Procfile").read_text(encoding="utf-8").strip()
        worker = Path("search_worker.py").read_text(encoding="utf-8")
        self.assertEqual(procfile, "web: gunicorn telegram_bootstrap:app")
        self.assertIn("def main():", worker)
        self.assertIn("run_one_job", worker)
        self.assertIn("BACKGROUND_WORKER_IDLE_SECONDS", worker)


if __name__ == "__main__":
    unittest.main()
