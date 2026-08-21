from pathlib import Path
import unittest


class BackgroundWorkerEntrypointTests(unittest.TestCase):
    def test_worker_is_separate_from_canonical_web_process(self):
        procfile = Path("Procfile").read_text(encoding="utf-8").strip()
        bootstrap = Path("private_global_bootstrap.py").read_text(encoding="utf-8")
        worker = Path("search_worker.py").read_text(encoding="utf-8")

        self.assertEqual(procfile, "web: gunicorn private_global_bootstrap:app")
        self.assertIn("from telegram_bootstrap import app", bootstrap)
        self.assertNotIn("search_worker", procfile)
        self.assertNotIn("search_worker", bootstrap)
        self.assertIn("def main():", worker)
        self.assertIn("run_availability_hunter_job", worker)
        self.assertIn("BACKGROUND_WORKER_IDLE_SECONDS", worker)

    def test_worker_refreshes_feedback_and_verification_lessons_each_batch(self):
        worker = Path("search_worker.py").read_text(encoding="utf-8")
        self.assertIn("def _runtime_generation_state", worker)
        self.assertIn('feedback_count', worker)
        self.assertIn('conflict_names', worker)
        self.assertIn('successful_names', worker)
        self.assertIn('next batch', worker.lower())
        self.assertIn('preferences["_runtime"]', worker)
        self.assertIn('update(search_jobs)', worker)


if __name__ == "__main__":
    unittest.main()
