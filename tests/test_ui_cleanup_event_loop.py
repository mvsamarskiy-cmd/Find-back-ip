import unittest
from pathlib import Path


class UiCleanupEventLoopTests(unittest.TestCase):
    def test_compact_telemetry_observer_does_not_observe_its_own_subtree(self):
        source = Path('static/ui_cleanup_r8.js').read_text(encoding='utf-8')

        # Regression for a production UI freeze: #largeSearchCompact is inserted
        # inside #largeSearchPanel and updateCompactTelemetry mutates that compact
        # node. Observing the whole panel subtree therefore creates an endless
        # MutationObserver microtask loop and starves taps/DOMContentLoaded.
        self.assertNotIn(
            "telemetryObserver.observe(panel, { childList: true, subtree: true",
            source,
        )
        self.assertIn("telemetryObserver.observe(telemetry, {", source)
        self.assertIn("telemetryObserver.observe(panel, {", source)
        self.assertIn("attributeFilter: ['hidden']", source)

    def test_compact_updates_are_idempotent(self):
        source = Path('static/ui_cleanup_r8.js').read_text(encoding='utf-8')
        self.assertIn("copy.textContent !== nextText", source)
        self.assertIn("compact.hidden !== panel.hidden", source)


if __name__ == '__main__':
    unittest.main()
