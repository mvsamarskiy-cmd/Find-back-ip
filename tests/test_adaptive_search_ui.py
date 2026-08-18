import unittest

import app


class AdaptiveSearchUiTests(unittest.TestCase):
    def setUp(self):
        self.body = app.app.test_client().get("/").get_data(as_text=True)

    def test_ui_declares_bounded_multi_batch_search(self):
        self.assertIn("MAX_EXTERNAL_CHECKS=100", self.body)
        self.assertIn("BATCH_SIZE=20", self.body)
        self.assertIn("MAX_BATCHES=5", self.body)
        self.assertIn("Запустити глибокий пошук", self.body)
        self.assertIn("safety cap 100", self.body)

    def test_target_is_number_of_usable_identity_bundles(self):
        self.assertIn("Ціль: 5 придатних", self.body)
        self.assertIn("Ціль: 10 придатних", self.body)
        self.assertIn("Ціль: 20 придатних", self.body)
        self.assertIn("afterOpportunities>=target", self.body)

    def test_follow_up_batches_send_prior_results_as_context(self):
        self.assertIn("function adaptiveContext", self.body)
        self.assertIn("exclude_names", self.body)
        self.assertIn("conflict_names", self.body)
        self.assertIn("successful_names", self.body)
        self.assertIn("generation_context:adaptiveContext(batch)", self.body)

    def test_browser_uses_batched_checked_endpoint_not_per_name_check_loop(self):
        self.assertIn("fetch('/api/ai-generate'", self.body)
        self.assertNotIn("fetch('/api/check/'+encodeURIComponent(row.name)", self.body)

    def test_partial_results_survive_failed_later_batch(self):
        self.assertIn("часткові результати збережено", self.body)
        self.assertIn("current.done=false", self.body)
        self.assertIn("saveHistory(current)", self.body)


if __name__ == "__main__":
    unittest.main()
