import os
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from global_search import build_search_plan, search_global
from private_mode import hash_secret_for_env, install_private_mode_routes, verify_secret


class PrivateGlobalModeTests(unittest.TestCase):
    def env(self):
        return {
            "PRIVATE_MODE_UNLOCK_HASH": hash_secret_for_env("open-test-mode", salt=b"unlock-test-salt"),
            "PRIVATE_MODE_LOCK_HASH": hash_secret_for_env("close-test-mode", salt=b"lock-test-salt!!"),
            "PRIVATE_MODE_SESSION_KEY": "test-session-key-that-is-longer-than-32-bytes",
        }

    def make_app(self, searcher=None):
        app = Flask(__name__)
        app.testing = True
        install_private_mode_routes(app, global_searcher=searcher or (lambda query, **kwargs: {"query": query, "results": []}))
        return app

    def test_scrypt_hash_round_trip(self):
        encoded = hash_secret_for_env("тестова-команда", salt=b"0123456789abcdef")
        self.assertTrue(verify_secret("тестова-команда", encoded))
        self.assertFalse(verify_secret("інша-команда", encoded))
        self.assertNotIn("тестова-команда", encoded)

    def test_private_route_is_hidden_without_authorized_session(self):
        with patch.dict(os.environ, self.env(), clear=False):
            client = self.make_app().test_client()
            response = client.post("/api/private-mode/search", json={"query": "open grants"}, base_url="https://localhost")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "Not found"})

    def test_unlock_search_and_lock_are_server_side(self):
        calls = []
        def fake_search(query, **kwargs):
            calls.append((query, kwargs))
            return {"query": query, "provider_status": "complete", "results": [{"title": "Verified test row", "url": "https://example.test"}]}

        with patch.dict(os.environ, self.env(), clear=False):
            client = self.make_app(fake_search).test_client()
            unlock = client.post("/api/private-mode/command", json={"command": "open-test-mode"}, base_url="https://localhost")
            self.assertEqual(unlock.get_json()["mode"], "private")
            cookie = unlock.headers.get("Set-Cookie", "")
            self.assertIn("HttpOnly", cookie); self.assertIn("Secure", cookie); self.assertIn("SameSite=Strict", cookie)
            self.assertEqual(client.get("/api/private-mode/state", base_url="https://localhost").get_json()["mode"], "private")
            search = client.post("/api/private-mode/search", json={"query": "AI grants", "category": "grant", "country": "PL"}, base_url="https://localhost")
            self.assertEqual(search.status_code, 200)
            self.assertEqual(calls, [("AI grants", {"category": "grant", "country": "PL"})])
            lock = client.post("/api/private-mode/command", json={"command": "close-test-mode"}, base_url="https://localhost")
            self.assertEqual(lock.get_json()["mode"], "public")
            self.assertEqual(client.get("/api/private-mode/state", base_url="https://localhost").get_json(), {"mode": "public"})

    def test_wrong_command_does_not_reveal_private_mode(self):
        with patch.dict(os.environ, self.env(), clear=False):
            response = self.make_app().test_client().post("/api/private-mode/command", json={"command": "not-the-command"}, base_url="https://localhost")
        self.assertEqual(response.get_json(), {"handled": False})

    def test_global_search_never_fabricates_when_provider_is_missing(self):
        with patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": ""}, clear=False):
            payload = search_global("AI grants for startups", category="grant", country="PL")
        self.assertEqual(payload["provider_status"], "unconfigured")
        self.assertEqual(payload["results"], [])
        self.assertTrue(payload["search_plan"])

    def test_search_plan_has_challenge_sources(self):
        plan = build_search_plan("AI robotics", category="challenge", country="EU")
        self.assertTrue(any("site:herox.com" in q or "site:xprize.org" in q for q in plan["queries"]))

    def test_client_contains_no_server_hash_variables(self):
        source = Path("static/private_global_mode.js").read_text(encoding="utf-8")
        self.assertIn("/api/private-mode/command", source)
        self.assertNotIn("PRIVATE_MODE_UNLOCK_HASH", source)
        self.assertNotIn("PRIVATE_MODE_LOCK_HASH", source)


if __name__ == "__main__":
    unittest.main()
