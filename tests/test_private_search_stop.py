import os
import unittest
from unittest.mock import patch

from flask import Flask

from money_opportunity_search import search_money_opportunities
from private_mode import hash_secret_for_env, install_private_mode_routes


class PrivateSearchStopTests(unittest.TestCase):
    def env(self):
        return {
            "PRIVATE_MODE_UNLOCK_HASH": hash_secret_for_env("open-test-mode", salt=b"unlock-test-salt"),
            "PRIVATE_MODE_LOCK_HASH": hash_secret_for_env("close-test-mode", salt=b"lock-test-salt!!"),
            "PRIVATE_MODE_SESSION_KEY": "test-session-key-that-is-longer-than-32-bytes",
        }

    def make_app(self):
        app = Flask(__name__)
        app.testing = True
        install_private_mode_routes(app)
        return app

    def test_stop_route_is_hidden_while_locked(self):
        with patch.dict(os.environ, self.env(), clear=False):
            response = self.make_app().test_client().post(
                "/api/private-mode/stop",
                json={"search_id": "nm-search-12345678"},
                base_url="https://localhost",
            )
        self.assertEqual(response.status_code, 404)

    def test_stop_route_validates_search_id_and_handles_unknown_active_search(self):
        with patch.dict(os.environ, self.env(), clear=False):
            client = self.make_app().test_client()
            unlock = client.post(
                "/api/private-mode/command",
                json={"command": "open-test-mode"},
                base_url="https://localhost",
            )
            self.assertEqual(unlock.get_json()["mode"], "private")

            invalid = client.post(
                "/api/private-mode/stop",
                json={"search_id": "bad"},
                base_url="https://localhost",
            )
            self.assertEqual(invalid.status_code, 400)

            unknown = client.post(
                "/api/private-mode/stop",
                json={"search_id": "nm-search-12345678"},
                base_url="https://localhost",
            )
            self.assertEqual(unknown.status_code, 200)
            self.assertEqual(unknown.get_json()["active"], False)
            self.assertEqual(unknown.get_json()["handled"], True)

    def test_cancelled_money_search_skips_provider_tor_and_direct_verification(self):
        calls = []

        def poster(url, **kwargs):
            calls.append(url)
            raise AssertionError("provider should not be called after cancellation")

        env = {
            "BRAVE_SEARCH_API_KEY": "",
            "BROWSER_EYE_URL": "http://browser.internal",
            "GLOBAL_SEARCH_BROWSER_TOKEN": "token",
            "TOR_OPPORTUNITY_SEARCH_ENABLED": "1",
            "MONEY_DIRECT_VERIFICATION_ENABLED": "1",
        }
        with patch.dict(os.environ, env, clear=False):
            payload = search_money_opportunities(
                "Знайди гранти і фінансування для компанії у Польщі",
                country="PL",
                poster=poster,
                cancel_checker=lambda: True,
            )

        self.assertEqual(calls, [])
        self.assertTrue(payload["stopped"])
        self.assertFalse(payload["tor_retrieval"]["attempted"])
        self.assertFalse(payload["direct_verification"]["enabled"])
        self.assertTrue(payload["direct_verification"]["skipped_due_to_stop"])


if __name__ == "__main__":
    unittest.main()
