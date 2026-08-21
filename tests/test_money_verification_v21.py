import os
import threading
import time
import unittest
from unittest.mock import patch

from money_opportunity_search import MAX_EXPANSION_CONCURRENCY, search_money_opportunities
from money_verification import apply_money_verification, verify_money_source


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"{}"
        self.text = ""
        self.headers = {}

    def json(self):
        return self._payload


def evidence(url, body, *, status=200):
    return {
        "provider_status": "complete",
        "http_status": status,
        "requested_url": url,
        "final_url": url,
        "body_text": body,
        "observed_at": "2026-08-21T17:00:00+00:00",
        "snapshot_sha256": "a" * 64,
        "public_contacts": {},
    }


class MoneyDirectVerificationTests(unittest.TestCase):
    def test_official_program_with_direct_active_evidence_can_verify_current_call(self):
        url = "https://parp.gov.pl/call/abc"
        row = {"url": url, "category": "grant", "official_source": True, "retrieval_score": 90}
        result = verify_money_source(
            row,
            evidence_fetcher=lambda _: evidence(
                url,
                "Applications open. Open call. Deadline 31 December 2026. Grant up to 500 000 PLN for SMEs in Poland.",
            ),
        )
        self.assertTrue(result["source_observed"])
        self.assertTrue(result["current_call_verified"])
        self.assertEqual(result["status"]["value"], "open")
        self.assertEqual(result["amount"]["currency"], "PLN")
        self.assertIn("sme", result["eligibility"]["applicant_types"])

    def test_market_listing_observation_never_becomes_current_call_verification(self):
        url = "https://olx.pl/oferta/abc"
        row = {"url": url, "category": "liquidation", "retrieval_score": 90}
        result = verify_money_source(
            row,
            evidence_fetcher=lambda _: evidence(url, "Wyprzedaż likwidacyjna. Cena 20 000 PLN. Oferta maszyny."),
        )
        self.assertTrue(result["source_observed"])
        self.assertFalse(result["current_call_verified"])

    def test_direct_verification_is_bounded_to_three_by_default(self):
        calls = []
        rows = [
            {"url": f"https://example{i}.org/x", "category": "grant", "retrieval_score": 90 - i}
            for i in range(8)
        ]

        def fetcher(url):
            calls.append(url)
            return evidence(url, "Open call. Applications open. Deadline 31 December 2026.")

        output = apply_money_verification(rows, evidence_fetcher=fetcher)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sum(1 for row in output if row.get("money_direct_verification")), 3)


class MoneySearchV21Tests(unittest.TestCase):
    def test_expansion_lanes_use_bounded_concurrency_after_exact_lane(self):
        lock = threading.Lock()
        active = 0
        maximum = 0
        calls = []

        def poster(url, **kwargs):
            nonlocal active, maximum
            if not url.endswith("/v1/web-search"):
                raise AssertionError(url)
            query = kwargs["json"]["query"]
            with lock:
                calls.append(query)
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.025)
            with lock:
                active -= 1
            index = len(calls)
            return FakeResponse(200, {"provider_status": "complete", "results": [{
                "title": f"Opportunity {index}",
                "description": "Tender contract 100 000 PLN",
                "url": f"https://example{index}.org/x",
            }]})

        env = {
            "BRAVE_SEARCH_API_KEY": "",
            "BROWSER_EYE_URL": "http://browser.internal",
            "GLOBAL_SEARCH_BROWSER_TOKEN": "token",
            "TOR_OPPORTUNITY_SEARCH_ENABLED": "0",
            "MONEY_DIRECT_VERIFICATION_ENABLED": "0",
        }
        query = "Знайди всі матеріальні можливості де є гроші для виробничої компанії"
        with patch.dict(os.environ, env, clear=False):
            payload = search_money_opportunities(query, country="PL", poster=poster)
        self.assertEqual(calls[0], query)
        self.assertGreaterEqual(maximum, 2)
        self.assertLessEqual(maximum, MAX_EXPANSION_CONCURRENCY)
        self.assertTrue(payload["results"])

    def test_search_attaches_direct_verification_and_projects_practical_score(self):
        counter = 0

        def poster(url, **kwargs):
            nonlocal counter
            if not url.endswith("/v1/web-search"):
                raise AssertionError(url)
            counter += 1
            return FakeResponse(200, {"provider_status": "complete", "results": [{
                "title": "PARP Startup Grant Open Call" if counter == 1 else f"Other opportunity {counter}",
                "description": "Applications open. Grant up to 500 000 PLN. Deadline 31 December 2026.",
                "url": "https://parp.gov.pl/call/startup" if counter == 1 else f"https://example{counter}.org/x",
            }]})

        def fetcher(url):
            return evidence(url, "Applications open. Open call. Deadline 31 December 2026. Grant up to 500 000 PLN for SMEs in Poland.")

        env = {
            "BRAVE_SEARCH_API_KEY": "",
            "BROWSER_EYE_URL": "http://browser.internal",
            "GLOBAL_SEARCH_BROWSER_TOKEN": "token",
            "TOR_OPPORTUNITY_SEARCH_ENABLED": "0",
            "MONEY_DIRECT_VERIFICATION_ENABLED": "1",
        }
        with patch.dict(os.environ, env, clear=False):
            payload = search_money_opportunities(
                "Знайди грант для SME у Польщі", country="PL", poster=poster,
                evidence_fetcher=fetcher,
            )
        self.assertGreaterEqual(payload["direct_verification"]["attempted_count"], 1)
        official = next(record for record in payload["money_records"] if "parp.gov.pl" in " ".join(record["source_urls"]))
        self.assertTrue(official["source_observed"])
        self.assertTrue(official["current_call_verified"])
        projected = next(row for row in payload["results"] if "parp.gov.pl" in row.get("url", ""))
        self.assertEqual(projected["fit"]["score"], official["practical_ranking"]["score"])
        self.assertEqual(projected["money_record"]["opportunity_id"], official["opportunity_id"])


if __name__ == "__main__":
    unittest.main()
