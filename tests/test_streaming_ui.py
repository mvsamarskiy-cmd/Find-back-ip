from pathlib import Path
import unittest

from telegram_bootstrap import app


class StreamingUiTests(unittest.TestCase):
    def test_home_loads_streaming_client_after_inline_ui(self):
        response = app.test_client().get("/")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('<script src="/static/streaming.js"></script>', body)
        self.assertLess(body.index("restoreSession();"), body.index('/static/streaming.js'))

    def test_client_consumes_ndjson_and_keeps_newest_feed_first(self):
        source = Path("static/streaming.js").read_text(encoding="utf-8")
        self.assertIn("/api/ai-generate-stream", source)
        self.assertIn("response.body.getReader", source)
        self.assertIn("received_seq", source)
        self.assertIn("newestFirst(current.results)", source)
        self.assertIn("startSearch = async function startStreamingSearch", source)
        self.assertIn("activeController.abort", Path("templates/index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
