import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class BrowserEyeTorStartupTests(unittest.TestCase):
    def test_startup_uses_real_torrc_not_dev_null(self):
        source = (ROOT / "browser_eye_start.sh").read_text(encoding="utf-8")
        self.assertIn("TORRC=/tmp/browser-eye-torrc", source)
        self.assertIn('tor --verify-config -f "$TORRC"', source)
        self.assertIn('tor -f "$TORRC" &', source)
        self.assertNotIn("-f /dev/null", source)
        self.assertIn("SocksPort 127.0.0.1:9050", source)
        self.assertIn("DataDirectory /tmp/tor-data", source)


if __name__ == "__main__":
    unittest.main()
