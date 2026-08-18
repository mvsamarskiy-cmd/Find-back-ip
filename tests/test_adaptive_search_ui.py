import unittest

import app


class AdaptiveSearchUiTests(unittest.TestCase):
    def setUp(self):
        self.body = app.app.test_client().get("/").get_data(as_text=True)

    def test_ui_keeps_bounded_multi_batch_search_under_simple_controls(self):
        self.assertIn("MAX_EXTERNAL_CHECKS=100", self.body)
        self.assertIn("BATCH_SIZE=20", self.body)
        self.assertIn("MAX_BATCHES=5", self.body)
        self.assertIn('id="startBtn"', self.body)
        self.assertIn('id="stopBtn"', self.body)
        self.assertIn("Continue", self.body)

    def test_follow_up_batches_send_prior_results_as_context(self):
        self.assertIn("function adaptiveContext", self.body)
        self.assertIn("exclude_names", self.body)
        self.assertIn("conflict_names", self.body)
        self.assertIn("successful_names", self.body)
        self.assertIn("generation_context:adaptiveContext(batch)", self.body)

    def test_browser_uses_batched_checked_endpoint(self):
        self.assertIn("fetch('/api/ai-generate'", self.body)
        self.assertIn("required_resources:resources", self.body)
        self.assertNotIn("fetch('/api/check/'+encodeURIComponent(row.name)", self.body)

    def test_stop_preserves_partial_session_and_feedback(self):
        self.assertIn("function stopSearch()", self.body)
        self.assertIn("activeController.abort()", self.body)
        self.assertIn("часткові результати збережено", self.body)
        self.assertIn("feedback", self.body)
        self.assertIn("shortlist", self.body)
        self.assertIn("directionAnchors", self.body)

    def test_results_append_across_continue_runs(self):
        self.assertIn("current.results.push", self.body)
        self.assertIn("current.runs.push(run)", self.body)
        self.assertNotIn("results:[]};saveHistory", self.body)


if __name__ == "__main__":
    unittest.main()
