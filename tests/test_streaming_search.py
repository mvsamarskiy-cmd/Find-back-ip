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
    def _payload(resource, status="claimable"):
        verdict = "available_verified" if status == "claimable" else "taken"
        signal = "claimable" if status == "claimable" else "exists"
        row = {
            "status": status,
            "detail": "fixture",
            "url": "https://example.test/" + resource,
            "source": "fixture_provider",
            "method": "fixture",
            "confidence": 0.99,
            "occupancy": "not_found" if status == "claimable" else "occupied",
            "claimability": "confirmed" if status == "claimable" else "not_claimable",
        }
        return {
            "availability": {resource: row},
            "verification": {
                resource: {
                    "platform": resource,
                    "handle": "fixture",
                    "verdict": verdict,
                    "confidence": 0.99,
                    "evidence": [{"signal": signal, "source": "fixture_provider"}],
                    "reason": "fixture",
                }
            },
        }

    def _post(self, resources=None, count=1):
        resources = resources or ["com"]
        # buffered=True consumes the lazy iterator while unittest.mock patches
        # are still active. Production responses remain genuinely streamed.
        return self.client.post(
            "/api/ai-generate-stream",
            json={
                "brief": "car marketplace",
                "count": count,
                "resources": resources,
                "required_resources": resources,
                "preferences": {},
            },
            buffered=True,
        )

    @staticmethod
    def _events(response):
        return [json.loads(line) for line in response.get_data(as_text=True).splitlines() if line.strip()]

    @patch.dict(os.environ, {}, clear=True)
    def test_generation_phase_is_streamed_before_ai_generation_finishes(self):
        generated = [{"name": "Alpha"}]
        with patch.object(app_module, "generate_ai_with_context", return_value=generated) as generator:
            with patch.object(app_module, "check_all", side_effect=lambda name, resources=None: self._payload(list(resources)[0])):
                response = self.client.post(
                    "/api/ai-generate-stream",
                    json={
                        "brief": "car marketplace",
                        "count": 1,
                        "resources": ["com"],
                        "required_resources": ["com"],
                        "preferences": {},
                    },
                    buffered=False,
                )
                chunks = iter(response.response)
                first_chunk = next(chunks)
                first = json.loads(first_chunk.decode() if isinstance(first_chunk, bytes) else first_chunk)
                generator.assert_not_called()
                response.close()

        self.assertEqual(first["type"], "phase")
        self.assertEqual(first["phase"], "generating")

    @patch.dict(os.environ, {}, clear=True)
    def test_candidate_is_emitted_before_resources_and_fast_resource_arrives_first(self):
        generated = [{"name": "Alpha", "reason": "fixture"}]

        def fake_check(name, resources=None):
            resource = list(resources)[0]
            if resource == "com":
                time.sleep(0.08)
            return self._payload(resource, "claimable")

        with patch.object(app_module, "generate_ai_with_context", return_value=generated):
            with patch.object(app_module, "check_all", side_effect=fake_check):
                response = self._post(resources=["com", "x"])

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content_type.startswith("application/x-ndjson"))
        self.assertEqual(response.headers.get("X-Accel-Buffering"), "no")
        events = self._events(response)
        self.assertEqual(events[0]["type"], "phase")
        self.assertEqual(events[0]["phase"], "generating")
        generated_phase = next(event for event in events if event.get("phase") == "generated")
        generated_index = events.index(generated_phase)
        candidate_index = next(i for i, event in enumerate(events) if event["type"] == "candidate")
        self.assertLess(generated_index, candidate_index)
        candidate = events[candidate_index]
        self.assertEqual(candidate["row"]["name"], "Alpha")
        resource_events = [event for event in events if event["type"] == "resource"]
        self.assertEqual([event["resource"] for event in resource_events], ["x", "com"])
        result = [event for event in events if event["type"] == "result"][0]["row"]
        self.assertEqual(result["bundle_state"], "confirmed")
        self.assertEqual(set(result["availability"]), {"com", "x"})
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["completed_resource_checks"], 2)

    @patch.dict(os.environ, {}, clear=True)
    def test_resource_failure_is_unknown_but_candidate_is_still_delivered(self):
        generated = [{"name": "Partial", "reason": "fixture"}]

        def fake_check(name, resources=None):
            resource = list(resources)[0]
            if resource == "x":
                raise RuntimeError("fixture failure")
            return self._payload(resource, "claimable")

        with patch.object(app_module, "generate_ai_with_context", return_value=generated):
            with patch.object(app_module, "check_all", side_effect=fake_check):
                response = self._post(resources=["com", "x"])

        events = self._events(response)
        failed = [event for event in events if event["type"] == "resource" and event.get("error")]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["resource"], "x")
        self.assertEqual(failed[0]["availability"]["status"], "unknown")
        result = [event for event in events if event["type"] == "result"][0]["row"]
        self.assertEqual(result["availability"]["x"]["status"], "unknown")
        self.assertNotEqual(result["bundle_state"], "confirmed")
        done = events[-1]
        self.assertEqual(done["delivered"], 1)
        self.assertEqual(done["errors"], 1)

    @patch.dict(os.environ, {}, clear=True)
    def test_generation_failure_is_an_explicit_stream_error(self):
        with patch.object(app_module, "generate_ai_with_context", side_effect=RuntimeError("fixture")):
            response = self._post(resources=["com"])
        events = self._events(response)
        self.assertEqual(events[0]["phase"], "generating")
        self.assertEqual(events[-1]["type"], "fatal_error")
        self.assertEqual(events[-1]["stage"], "generation")
        self.assertNotIn("fixture", events[-1]["message"])

    @patch.dict(os.environ, {}, clear=True)
    def test_each_resource_is_checked_exactly_once(self):
        generated = [{"name": "Alpha"}, {"name": "Beta"}]
        calls = []

        def fake_check(name, resources=None):
            resource = list(resources)[0]
            calls.append((str(name).lower(), resource))
            return self._payload(resource, "claimable")

        with patch.object(app_module, "generate_ai_with_context", return_value=generated):
            with patch.object(app_module, "check_all", side_effect=fake_check):
                response = self._post(resources=["com", "telegram"], count=2)

        events = self._events(response)
        self.assertEqual(len(calls), 4)
        self.assertEqual(set(calls), {
            ("alpha", "com"), ("alpha", "telegram"),
            ("beta", "com"), ("beta", "telegram"),
        })
        self.assertEqual(events[-1]["total_resource_checks"], 4)
        self.assertEqual(events[-1]["completed_resource_checks"], 4)

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
