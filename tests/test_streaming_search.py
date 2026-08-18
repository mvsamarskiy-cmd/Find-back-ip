import json
import os
import time
import unittest
from unittest.mock import patch

import app as app_module
from telegram_bootstrap import app


class StreamingSearchTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @staticmethod
    def _availability(status="claimable"):
        return {
            "availability": {
                "com": {
                    "status": status,
                    "detail": "fixture",
                    "url": "https://example.test",
                    "source": "namecom_core_api" if status == "claimable" else "verisign_rdap",
                    "method": "fixture",
                    "confidence": 0.99,
                    "occupancy": "not_found" if status == "claimable" else "occupied",
                    "claimability": "confirmed" if status == "claimable" else "not_claimable",
                }
            }
        }

    def _post(self, count=2):
        # buffered=True consumes the lazy streaming iterator before unittest.mock
        # patches leave scope, while production remains genuinely streamed.
        return self.client.post(
            "/api/ai-generate-stream",
            json={
                "brief": "car marketplace",
                "count": count,
                "resources": ["com"],
                "required_resources": ["com"],
                "preferences": {},
            },
            buffered=True,
        )

    @staticmethod
    def _events(response):
        return [json.loads(line) for line in response.get_data(as_text=True).splitlines() if line.strip()]

    @patch.dict(os.environ, {}, clear=True)
    def test_stream_yields_fast_candidate_before_slow_candidate(self):
        generated = [
            {"name": "Slow", "reason": "slow fixture"},
            {"name": "Fast", "reason": "fast fixture"},
        ]

        def fake_check(name, resources=None):
            if str(name).lower() == "slow":
                time.sleep(0.08)
            return self._availability("claimable")

        with patch.object(app_module, "generate_ai_with_context", return_value=generated):
            with patch.object(app_module, "check_all", side_effect=fake_check):
                response = self._post(count=2)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content_type.startswith("application/x-ndjson"))
        self.assertEqual(response.headers.get("X-Accel-Buffering"), "no")
        events = self._events(response)
        self.assertEqual(events[0]["type"], "phase")
        result_events = [event for event in events if event["type"] == "result"]
        self.assertEqual([event["row"]["name"] for event in result_events], ["Fast", "Slow"])
        self.assertTrue(all(event["row"]["bundle_state"] == "confirmed" for event in result_events))
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["delivered"], 2)
        self.assertEqual(events[-1]["errors"], 0)

    @patch.dict(os.environ, {}, clear=True)
    def test_one_candidate_failure_does_not_destroy_partial_stream(self):
        generated = [{"name": "Broken"}, {"name": "Good"}]

        def fake_check(name, resources=None):
            if str(name).lower() == "broken":
                raise RuntimeError("fixture failure")
            return self._availability("claimable")

        with patch.object(app_module, "generate_ai_with_context", return_value=generated):
            with patch.object(app_module, "check_all", side_effect=fake_check):
                response = self._post(count=2)

        events = self._events(response)
        types = [event["type"] for event in events]
        self.assertIn("candidate_error", types)
        self.assertIn("result", types)
        done = events[-1]
        self.assertEqual(done["type"], "done")
        self.assertEqual(done["delivered"], 1)
        self.assertEqual(done["errors"], 1)

    def test_empty_resource_selection_is_rejected_before_generation(self):
        with patch.object(app_module, "generate_ai_with_context") as generator:
            response = self.client.post(
                "/api/ai-generate-stream",
                json={"brief": "car marketplace", "resources": []},
            )
        self.assertEqual(response.status_code, 400)
        generator.assert_not_called()


if __name__ == "__main__":
    unittest.main()
