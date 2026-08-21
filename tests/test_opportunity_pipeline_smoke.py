import os
import unittest
from unittest.mock import patch

from opportunity_pipeline_smoke import (
    maybe_start_pipeline_smoke,
    run_pipeline_smoke,
    summarize_pipeline_payload,
)


class OpportunityPipelineSmokeTests(unittest.TestCase):
    def test_pipeline_smoke_is_disabled_by_default(self):
        with patch.dict(os.environ, {"OPPORTUNITY_PIPELINE_STARTUP_SMOKE": ""}, clear=False):
            self.assertFalse(maybe_start_pipeline_smoke())

    def test_summary_contains_only_aggregate_opportunity_metrics(self):
        payload = {
            "provider_status": "complete",
            "requested_category": "all",
            "routed_category": "grant",
            "intent_routed": True,
            "intelligence_version": "opportunity-v1",
            "results": [
                {
                    "title": "SECRET TITLE",
                    "url": "https://secret.example/opportunity",
                    "description": "SECRET DESCRIPTION",
                    "official_source": True,
                    "normalized": True,
                    "opportunity": {
                        "amount": {"currency": "EUR", "max": 50000, "evidence": "secret amount evidence"},
                        "deadline": {"date": "2026-12-01", "evidence": "secret deadline evidence"},
                        "status": {"value": "open", "reason": "open_marker"},
                        "eligibility": {"applicant_types": ["startup"]},
                        "verification": {"source_verified": True, "http_status": 200},
                    },
                    "fit": {"score": 87, "label": "high", "blockers": []},
                },
                {
                    "title": "ANOTHER SECRET",
                    "url": "https://another.example/call",
                    "official_source": False,
                    "normalized": True,
                    "opportunity": {
                        "amount": None,
                        "deadline": None,
                        "status": {"value": "unknown"},
                        "eligibility": {},
                        "verification": {"source_verified": False},
                    },
                    "fit": {"score": 61, "label": "medium"},
                },
            ],
        }
        summary = summarize_pipeline_payload(payload, duration_ms=1234)
        self.assertEqual(summary["provider_status"], "complete")
        self.assertEqual(summary["routed_category"], "grant")
        self.assertTrue(summary["intent_routed"])
        self.assertEqual(summary["result_count"], 2)
        self.assertEqual(summary["normalized_count"], 2)
        self.assertEqual(summary["official_source_count"], 1)
        self.assertEqual(summary["source_verified_count"], 1)
        self.assertEqual(summary["with_amount_count"], 1)
        self.assertEqual(summary["with_deadline_count"], 1)
        self.assertEqual(summary["status_counts"], {"open": 1, "unknown": 1})
        self.assertEqual(summary["top_fit_score"], 87)
        self.assertEqual(summary["duration_ms"], 1234)
        rendered = repr(summary)
        self.assertNotIn("SECRET TITLE", rendered)
        self.assertNotIn("secret.example", rendered)
        self.assertNotIn("secret amount evidence", rendered)

    def test_run_smoke_exercises_natural_language_routing(self):
        calls = []

        def fake_searcher(query, **kwargs):
            calls.append((query, kwargs))
            return {
                "provider_status": "complete",
                "requested_category": "all",
                "routed_category": "grant",
                "intent_routed": True,
                "intelligence_version": "opportunity-v1",
                "results": [{
                    "normalized": True,
                    "official_source": True,
                    "opportunity": {
                        "amount": None,
                        "deadline": None,
                        "status": {"value": "open"},
                        "verification": {"source_verified": False},
                    },
                    "fit": {"score": 75},
                }],
            }

        summary = run_pipeline_smoke(searcher=fake_searcher)
        self.assertEqual(calls, [("AI grants for startups", {"category": "all", "country": "PL"})])
        self.assertEqual(summary["routed_category"], "grant")
        self.assertEqual(summary["result_count"], 1)
        self.assertEqual(summary["top_fit_score"], 75)

    def test_pipeline_error_returns_only_error_type(self):
        def explode(*_args, **_kwargs):
            raise RuntimeError("sensitive internal text should never be logged")

        summary = run_pipeline_smoke(searcher=explode)
        self.assertEqual(summary["provider_status"], "pipeline_error")
        self.assertEqual(summary["error_type"], "RuntimeError")
        self.assertNotIn("sensitive internal text", repr(summary))


if __name__ == "__main__":
    unittest.main()
