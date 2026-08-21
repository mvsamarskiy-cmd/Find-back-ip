from datetime import date
import unittest

from opportunity_intelligence import (
    enrich_payload,
    extract_amount,
    extract_deadline,
    extract_eligibility,
    infer_status,
)


class FakeResponse:
    def __init__(self, text, status_code=200, content_type="text/html"):
        self.text = text
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}


class OpportunityIntelligenceTests(unittest.TestCase):
    def test_extracts_euro_range(self):
        amount = extract_amount("Prize pool €50k–€150k for selected teams")
        self.assertEqual(amount["currency"], "EUR")
        self.assertEqual(amount["min"], 50_000)
        self.assertEqual(amount["max"], 150_000)
        self.assertEqual(amount["kind"], "range")

    def test_extracts_polish_million_amount(self):
        amount = extract_amount("Dofinansowanie PLN 2 mln na projekt")
        self.assertEqual(amount["currency"], "PLN")
        self.assertEqual(amount["max"], 2_000_000)

    def test_deadline_prefers_marker_context(self):
        deadline = extract_deadline("Applications open. Submission deadline: 14 November 2026.")
        self.assertEqual(deadline["date"], "2026-11-14")
        self.assertGreaterEqual(deadline["confidence"], 0.9)

    def test_status_closes_when_deadline_has_passed(self):
        status = infer_status(
            "Applications open",
            {"date": "2026-01-01"},
            today=date(2026, 8, 21),
        )
        self.assertEqual(status["value"], "closed")
        self.assertEqual(status["reason"], "deadline_passed")

    def test_eligibility_keeps_unknown_individual_state_conservative(self):
        eligibility = extract_eligibility("Funding for SMEs and startups in Poland")
        self.assertIn("sme", eligibility["applicant_types"])
        self.assertIn("startup", eligibility["applicant_types"])
        self.assertIn("PL", eligibility["geography"])
        self.assertIsNone(eligibility["individual_allowed"])

    def test_explicit_individual_eligibility_is_observed(self):
        eligibility = extract_eligibility("Open to individuals and researchers worldwide")
        self.assertTrue(eligibility["individual_allowed"])
        self.assertIn("individual", eligibility["applicant_types"])
        self.assertIn("researcher", eligibility["applicant_types"])
        self.assertIn("GLOBAL", eligibility["geography"])

    def test_enrichment_verifies_known_source_and_normalizes_fields(self):
        payload = {
            "provider": "browser_eye_google",
            "provider_status": "complete",
            "results": [{
                "title": "PARP AI support programme",
                "description": "Funding for SMEs in Poland",
                "url": "https://www.parp.gov.pl/component/grants/grants/ai-support",
                "host": "parp.gov.pl",
                "category": "business_aid",
                "retrieval_score": 82,
                "source_tier": "official",
                "source_name": "PARP",
                "source_country": "PL",
                "official_source": True,
            }],
        }

        def requester(url, **kwargs):
            self.assertIn("parp.gov.pl", url)
            self.assertFalse(kwargs.get("allow_redirects"))
            return FakeResponse("""
                <html><body>
                <h1>AI support</h1>
                <p>Applications open for SMEs and startups in Poland.</p>
                <p>Maximum funding: PLN 2 mln.</p>
                <p>Submission deadline: 14 November 2026.</p>
                </body></html>
            """)

        enriched = enrich_payload(
            payload,
            query="funding for SME in Poland over PLN 1 mln",
            country="PL",
            requester=requester,
        )
        row = enriched["results"][0]
        self.assertEqual(enriched["intelligence_version"], "opportunity-v1")
        self.assertTrue(row["opportunity"]["verification"]["source_verified"])
        self.assertEqual(row["opportunity"]["amount"]["currency"], "PLN")
        self.assertEqual(row["opportunity"]["amount"]["max"], 2_000_000)
        self.assertEqual(row["opportunity"]["deadline"]["date"], "2026-11-14")
        self.assertEqual(row["opportunity"]["status"]["value"], "open")
        self.assertIn("sme", row["opportunity"]["eligibility"]["applicant_types"])
        self.assertGreaterEqual(row["fit"]["score"], 70)
        self.assertNotIn("page_text", row["opportunity"]["verification"])


if __name__ == "__main__":
    unittest.main()
