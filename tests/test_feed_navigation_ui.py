from pathlib import Path
import unittest

from telegram_bootstrap import app


class LargeFeedNavigationUiTests(unittest.TestCase):
    def test_navigation_client_loads_after_sync_and_progress_layers(self):
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('/static/feed_navigation.js', body)
        self.assertLess(body.index('/static/resource_progress.js'), body.index('/static/feed_navigation.js'))
        self.assertLess(body.index('/static/session_sync.js'), body.index('/static/feed_navigation.js'))

    def test_feed_is_newest_first_bounded_and_not_alphabetical(self):
        source = Path("static/feed_navigation.js").read_text(encoding="utf-8")
        self.assertIn("received_seq", source)
        self.assertIn("received_at", source)
        self.assertIn("return 0; // stable insertion order; deliberately never alphabetical", source)
        self.assertNotIn("localeCompare", source)
        self.assertIn("const PAGE_SIZE = 60", source)
        self.assertIn("filtered.slice(0, visibleLimit)", source)
        self.assertIn("Показати ще", source)

    def test_filters_do_not_call_unverified_names_free(self):
        source = Path("static/feed_navigation.js").read_text(encoding="utf-8")
        self.assertIn("allGreen(row)", source)
        self.assertIn("hasConflict(row)", source)
        self.assertIn("row?.bundle_state === 'promising'", source)
        self.assertIn("unresolved", source)
        self.assertNotIn("likely available", source.lower())
        self.assertNotIn("вільн", source.lower())


if __name__ == "__main__":
    unittest.main()
