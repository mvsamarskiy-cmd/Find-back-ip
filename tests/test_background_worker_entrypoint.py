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
