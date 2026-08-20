from pathlib import Path
import unittest

from telegram_bootstrap import app


class LargeFeedNavigationUiTests(unittest.TestCase):
    def test_navigation_client_loads_after_sync_and_progress_layers(self):
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('/static/feed_navigation.js?v=4', body)
        self.assertLess(body.index('/static/resource_progress.js'), body.index('/static/feed_navigation.js?v=4'))
        self.assertLess(body.index('/static/session_sync.js'), body.index('/static/feed_navigation.js?v=4'))

    def test_feed_is_newest_first_paginated_and_not_alphabetical(self):
        source = Path("static/feed_navigation.js").read_text(encoding="utf-8")
        self.assertIn("received_seq", source)
        self.assertIn("received_at", source)
        self.assertIn("return 0;", source)
        self.assertNotIn("localeCompare", source)
        self.assertIn("const PAGE_SIZE = 25", source)
        self.assertIn("function slicePage", source)
        self.assertIn("function paginationMarkup", source)
        self.assertIn("data-page-kind", source)
        self.assertNotIn("Показати ще", source)

    def test_all_three_result_views_are_paginated(self):
        source = Path("static/feed_navigation.js").read_text(encoding="utf-8")
        self.assertIn("const pages = { feed: 1, recommended: 1, shortlist: 1 }", source)
        self.assertIn("'recommendedGrid'", source)
        self.assertIn("'feedGrid'", source)
        self.assertIn("'shortlistGrid'", source)
        self.assertIn("pageGrid(", source)
        diagnostics = app.test_client().get("/api/verification/diagnostics").get_json()
        navigation = diagnostics["large_feed_navigation"]
        self.assertTrue(navigation["pagination"])
        self.assertEqual(navigation["render_page_size"], 25)
        self.assertEqual(navigation["views_paginated"], ["feed", "recommended", "shortlist"])

    def test_filters_preserve_truth_and_turbo_does_not_hide_feedback_rows(self):
        source = Path("static/feed_navigation.js").read_text(encoding="utf-8")
        self.assertIn("allGreen(row)", source)
        self.assertIn("hasConflict(row)", source)
        self.assertIn("row?.bundle_state === 'promising'", source)
        self.assertIn("unresolved", source)
        self.assertNotIn("likely available", source.lower())
        self.assertIn("return !allGreen(row) && !hasConflict(row)", source)
        self.assertIn("return turboRunRows(rows);", source)
        self.assertIn("activeRows.filter(allGreen)", source)
        self.assertNotIn("turboRunRows(rows).filter(allGreen)", source)


if __name__ == "__main__":
    unittest.main()
