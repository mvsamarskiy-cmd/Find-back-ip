import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PrivateStopMobileFixTests(unittest.TestCase):
    def test_bootstrap_loads_stop_fix_after_private_controller(self):
        bootstrap = (ROOT / "private_global_bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("PRIVATE_STOP_MOBILE_FIX_TAG", bootstrap)
        self.assertIn("/static/private_stop_mobile_fix.js?v=1", bootstrap)
        self.assertLess(
            bootstrap.index("PRIVATE_GLOBAL_MODE_TAG,"),
            bootstrap.index("PRIVATE_STOP_MOBILE_FIX_TAG,"),
        )

    def test_mobile_fix_reenables_stop_only_while_private_search_is_busy(self):
        source = (ROOT / "static" / "private_stop_mobile_fix.js").read_text(encoding="utf-8")
        self.assertIn("document.body.classList.contains('nm-private-global')", source)
        self.assertIn("return isPrivate() && start.disabled", source)
        self.assertIn("if (stop.disabled !== next) stop.disabled = next", source)
        self.assertIn("setDisabled(!active)", source)
        self.assertIn("setStyle('pointerEvents', active ? 'auto' : 'none')", source)
        self.assertIn("stopSearch();", source)
        self.assertIn("event.stopImmediatePropagation()", source)
        self.assertIn("new MutationObserver(syncStopState)", source)

    def test_stop_observer_does_not_rewrite_the_observed_disabled_state_unconditionally(self):
        source = (ROOT / "static" / "private_stop_mobile_fix.js").read_text(encoding="utf-8")
        self.assertIn("observer.observe(stop, { attributes: true, attributeFilter: ['disabled'] })", source)
        self.assertNotIn("stop.disabled = !active", source)
        self.assertNotIn("stop.disabled = true;", source)


if __name__ == "__main__":
    unittest.main()
