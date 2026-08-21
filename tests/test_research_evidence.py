import os
import unittest
from unittest.mock import patch

from flask import Flask

from private_research import install_private_research_routes
from research_evidence import extract_public_contacts, fetch_research_evidence, research_evidence_capabilities


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"{}"

    def json(self):
        return self._payload


class ResearchEvidenceTests(unittest.TestCase):
    def test_extracts_only_observed_public_contact_shapes(self):
        text = (
            "Contact: editor@example.org\n"
            "Phone +48 600 700 800\n"
            "Telegram: @reporter_box\n"
            "Matrix @desk:matrix.example\n"
            "XMPP: newsroom@jabber.example\n"
        )
        links = [
            {"url": "https://signal.me/#p/+48600111222", "title": "Signal"},
            {"url": "https://t.me/source_channel", "title": "Telegram"},
            {"url": "mailto:tips@example.net", "title": "Mail"},
        ]
        result = extract_public_contacts(text, links)
        self.assertIn("editor@example.org", result["emails"])
        self.assertIn("tips@example.net", result["emails"])
        self.assertIn("+48 600 700 800", result["phones"])
        self.assertIn("@reporter_box", result["telegram"])
        self.assertIn("https://t.me/source_channel", result["telegram"])
        self.assertIn("https://signal.me/#p/+48600111222", result["signal"])
        self.assertIn("@desk:matrix.example", result["matrix"])
        self.assertIn("newsroom@jabber.example", result["xmpp"])
        self.assertEqual(result["scope"], "publicly_observed_source_content_only")

    def test_fetch_preserves_original_url_line_breaks_links_and_snapshot(self):
        observed_text = "Heading\nPrice: 500 EUR\nContact: desk@example.org\nSecond paragraph"
        payload = {
            "provider_status": "complete",
            "transport": "tor",
            "requested_url": "https://example.org/post",
            "final_url": "https://example.org/post",
            "host": "example.org",
            "http_status": 200,
            "title": "Observed page",
            "body_text": observed_text,
            "description": "Heading Price: 500 EUR",
            "links": [
                {"url": "https://example.org/about", "title": "About"},
                {"url": "mailto:desk@example.org", "title": "Email"},
            ],
            "verification": {"verified": False, "state": "tor_retrieval_evidence"},
        }
        calls = []

        def poster(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse(payload=payload)

        with patch.dict(os.environ, {
            "BROWSER_EYE_URL": "https://browser.internal",
            "GLOBAL_SEARCH_BROWSER_TOKEN": "token",
        }, clear=False):
            result = fetch_research_evidence("https://example.org/post", poster=poster)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "https://browser.internal/v1/tor-fetch")
        self.assertEqual(calls[0][1]["json"]["url"], "https://example.org/post")
        self.assertEqual(result["requested_url"], "https://example.org/post")
        self.assertEqual(result["body_text"], observed_text)
        self.assertIn("\n", result["body_text"])
        self.assertEqual(result["links"][0]["url"], "https://example.org/about")
        self.assertIn("desk@example.org", result["public_contacts"]["emails"])
        self.assertEqual(len(result["snapshot_sha256"]), 64)
        self.assertTrue(result["source_preserved"])
        self.assertFalse(result["verification"]["verified"])

    def test_unconfigured_fails_closed_without_fabricating_source(self):
        with patch.dict(os.environ, {"BROWSER_EYE_URL": "", "GLOBAL_SEARCH_BROWSER_TOKEN": ""}, clear=False):
            result = fetch_research_evidence("https://example.org/")
        self.assertEqual(result["provider_status"], "unconfigured")
        self.assertNotIn("body_text", result)

    def test_capabilities_are_read_only_and_do_not_claim_verification(self):
        caps = research_evidence_capabilities()
        self.assertTrue(caps["original_url_preserved"])
        self.assertTrue(caps["public_contact_extraction"])
        self.assertFalse(caps["login_automation"])
        self.assertFalse(caps["form_submission"])
        self.assertFalse(caps["purchase_automation"])
        self.assertEqual(caps["truth_semantics"], "source_retrieval_not_fact_verification")


class PrivateResearchRouteTests(unittest.TestCase):
    def _app(self, fetcher):
        app = Flask(__name__)
        app.testing = True
        install_private_research_routes(app, evidence_fetcher=fetcher)
        return app

    def test_locked_private_research_route_is_hidden(self):
        app = self._app(lambda url: {"provider_status": "complete", "requested_url": url})
        with patch("private_research._private_active", return_value=False):
            response = app.test_client().post("/api/private-mode/evidence", json={"url": "https://example.org"})
        self.assertEqual(response.status_code, 404)

    def test_private_research_route_returns_source_payload(self):
        app = self._app(lambda url: {
            "provider_status": "complete",
            "requested_url": url,
            "body_text": "raw evidence",
            "verification": {"verified": False},
        })
        with patch("private_research._private_active", return_value=True):
            response = app.test_client().post("/api/private-mode/evidence", json={"url": "https://example.org/source"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["requested_url"], "https://example.org/source")


if __name__ == "__main__":
    unittest.main()
