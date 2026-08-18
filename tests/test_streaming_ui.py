from pathlib import Path
import unittest

from telegram_bootstrap import app


class StreamingUiTests(unittest.TestCase):
    def test_home_loads_streaming_clients_after_inline_ui_in_order(self):
        response = app.test_client().get("/")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('<script src="/static/streaming.js"></script>', body)
        self.assertIn('<script src="/static/resource_progress.js"></script>', body)
        inline = body.index("restoreSession();")
        streaming = body.index('/static/streaming.js')
        progress = body.index('/static/resource_progress.js')
        self.assertLess(inline, streaming)
        self.assertLess(streaming, progress)

    def test_base_client_keeps_newest_first_feed(self):
        source = Path("static/streaming.js").read_text(encoding="utf-8")
        self.assertIn("received_seq", source)
        self.assertIn("newestFirst(current.results)", source)

    def test_resource_progress_client_consumes_incremental_events(self):
        source = Path("static/resource_progress.js").read_text(encoding="utf-8")
        self.assertIn("/api/ai-generate-stream", source)
        self.assertIn("response.body.getReader", source)
        self.assertIn("event.type === 'candidate'", source)
        self.assertIn("event.type === 'resource'", source)
        self.assertIn("event.type === 'result'", source)
        self.assertIn("status: 'checking'", source)
        self.assertIn("markInterrupted", source)
        self.assertIn("startSearch = async function resourceProgressSearch", source)
        self.assertIn("activeController.abort", Path("templates/index.html").read_text(encoding="utf-8"))

    def test_generation_activity_is_visible_without_exposing_model_reasoning(self):
        source = Path("static/resource_progress.js").read_text(encoding="utf-8")
        self.assertIn("activityCopy", source)
        self.assertIn("Інтерпретую запит", source)
        self.assertIn("Формую нові варіанти", source)
        self.assertIn("Враховую лайки, дизлайки й коментарі", source)
        self.assertIn("event.type === 'fatal_error'", source)
        self.assertIn("stopActivity", source)
        diagnostics = app.test_client().get("/api/verification/diagnostics").get_json()
        self.assertTrue(diagnostics["streaming_feed"]["pre_generation_phase_events"])
        self.assertTrue(diagnostics["streaming_feed"]["operational_activity_only"])


if __name__ == "__main__":
    unittest.main()
