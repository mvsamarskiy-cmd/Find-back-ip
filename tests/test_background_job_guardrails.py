import unittest
from unittest.mock import patch

import background_job_guardrails as guardrails
import background_search_api
import session_api
from background_jobs import SearchJobStore
from session_store import SessionStore
from telegram_bootstrap import app


class BackgroundAdmissionPolicyTests(unittest.TestCase):
    def test_pending_job_limit_is_explicit(self):
        with patch.object(guardrails, "MAX_PENDING_JOBS_PER_SESSION", 1):
            with self.assertRaises(guardrails.BackgroundJobLimitError) as raised:
                guardrails.evaluate_admission(
                    session_active=1,
                    session_pending=1,
                    global_active=1,
                    used_24h=500,
                    requested_checks=500,
                )
        self.assertEqual(raised.exception.code, "pending_job_limit")
        self.assertEqual(raised.exception.http_status, 429)

    def test_rolling_budget_reserves_requested_work(self):
        with patch.object(guardrails, "MAX_SESSION_24H_CHECKS", 1000):
            with self.assertRaises(guardrails.BackgroundJobLimitError) as raised:
                guardrails.evaluate_admission(
                    session_active=0,
                    session_pending=0,
                    global_active=0,
                    used_24h=800,
                    requested_checks=300,
                )
        self.assertEqual(raised.exception.code, "daily_check_budget")
        self.assertEqual(raised.exception.details["limit"], 1000)

    def test_global_capacity_is_service_busy_not_fake_session_error(self):
        with patch.object(guardrails, "MAX_GLOBAL_ACTIVE_JOBS", 2):
            with self.assertRaises(guardrails.BackgroundJobLimitError) as raised:
                guardrails.evaluate_admission(
                    session_active=0,
                    session_pending=0,
                    global_active=2,
                    used_24h=0,
                    requested_checks=100,
                )
        self.assertEqual(raised.exception.code, "global_queue_capacity")
        self.assertEqual(raised.exception.http_status, 503)


class BackgroundAdmissionApiTests(unittest.TestCase):
    def setUp(self):
        self.session_store = SessionStore("sqlite+pysqlite:///:memory:")
        self.job_store = SearchJobStore(self.session_store)
        self.session_patch = patch.object(session_api, "STORE", self.session_store)
        self.job_patch = patch.object(background_search_api, "JOB_STORE", self.job_store)
        self.session_patch.start()
        self.job_patch.start()
        self.client = app.test_client()
        self.session = self._create_session("guardrail-a")
        self.headers = {session_api.TOKEN_HEADER: self.session["session_token"]}

    def tearDown(self):
        self.job_patch.stop()
        self.session_patch.stop()

    def _create_session(self, client_id):
        response = self.client.post("/api/sessions", json={
            "client_session_id": client_id,
            "title": "Guardrail fixture",
            "prompt_history": [],
            "resources": ["com"],
            "runs": [],
            "feedback": {},
            "batch_counter": 0,
        })
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def _payload(self, target=500):
        return {
            "brief": "Коротка назва для сервісу автомобілів",
            "resources": ["com"],
            "required_resources": ["com"],
            "preferences": {},
            "target_count": target,
            "batch_size": 20,
        }

    def test_second_pending_job_is_rejected_until_first_is_cancelled(self):
        path = f"/api/sessions/{self.session['session_id']}/search-jobs"
        first = self.client.post(path, json=self._payload(), headers=self.headers)
        self.assertEqual(first.status_code, 202)

        blocked = self.client.post(path, json=self._payload(), headers=self.headers)
        self.assertEqual(blocked.status_code, 429)
        body = blocked.get_json()
        self.assertEqual(body["error_type"], "BackgroundSearchLimitExceeded")
        self.assertEqual(body["limit_code"], "pending_job_limit")
        self.assertIn("Retry-After", blocked.headers)

        job_id = first.get_json()["job"]["id"]
        cancelled = self.client.post(path + f"/{job_id}/cancel", headers=self.headers)
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.get_json()["job"]["state"], "cancelled")

        replacement = self.client.post(path, json=self._payload(), headers=self.headers)
        self.assertEqual(replacement.status_code, 202)

    def test_global_capacity_rejects_other_session_with_503(self):
        first_path = f"/api/sessions/{self.session['session_id']}/search-jobs"
        first = self.client.post(first_path, json=self._payload(), headers=self.headers)
        self.assertEqual(first.status_code, 202)

        other = self._create_session("guardrail-b")
        other_headers = {session_api.TOKEN_HEADER: other["session_token"]}
        other_path = f"/api/sessions/{other['session_id']}/search-jobs"
        with patch.object(guardrails, "MAX_GLOBAL_ACTIVE_JOBS", 1):
            blocked = self.client.post(other_path, json=self._payload(), headers=other_headers)
        self.assertEqual(blocked.status_code, 503)
        self.assertEqual(blocked.get_json()["limit_code"], "global_queue_capacity")

    def test_capabilities_publish_non_secret_admission_limits(self):
        response = self.client.get("/api/background-search")
        self.assertEqual(response.status_code, 200)
        admission = response.get_json()["admission_control"]
        self.assertTrue(admission["enabled"])
        self.assertEqual(admission["max_pending_jobs_per_session"], guardrails.MAX_PENDING_JOBS_PER_SESSION)
        self.assertEqual(admission["max_active_jobs_per_session"], guardrails.MAX_ACTIVE_JOBS_PER_SESSION)
        self.assertEqual(admission["budget_window_hours"], 24)
        self.assertTrue(admission["terminal_budget_uses_delivered_count"])


if __name__ == "__main__":
    unittest.main()
