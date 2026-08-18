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
        self.assertIn("return 0;", source)
        self.assertNotIn("localeCompare", source)
        self.assertIn("const PAGE_SIZE = 60", source)
        self.assertIn("filtered.slice(0, visibleLimit)", source)
        self.assertIn("Показати ще", source)

    def test_normal_filters_do_not_promote_unverified_names_to_free(self):
        source = Path("static/feed_navigation.js").read_text(encoding="utf-8")
        self.assertIn("allGreen(row)", source)
        self.assertIn("hasConflict(row)", source)
        self.assertIn("row?.bundle_state === 'promising'", source)
        self.assertIn("unresolved", source)
        self.assertNotIn("likely available", source.lower())
        # Free wording is now intentionally present only for Turbo's strict-green
        # presentation. The promising classifier still requires !allGreen.
        self.assertIn("return !allGreen(row) && !hasConflict(row)", source)
        self.assertIn("turboRunRows(rows).filter(allGreen)", source)


if __name__ == "__main__":
    unittest.main()
