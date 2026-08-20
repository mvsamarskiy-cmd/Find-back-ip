import unittest
from unittest.mock import patch

import background_search_api
import session_api
from background_jobs import SearchJobStore
from session_store import SessionStore
from telegram_bootstrap import app


class BackgroundSearchApiTests(unittest.TestCase):
    def setUp(self):
        self.session_store = SessionStore("sqlite+pysqlite:///:memory:")
        self.job_store = SearchJobStore(self.session_store)
        self.session_patch = patch.object(session_api, "STORE", self.session_store)
        self.job_patch = patch.object(background_search_api, "JOB_STORE", self.job_store)
        self.session_patch.start()
        self.job_patch.start()
        self.client = app.test_client()
        created = self.client.post("/api/sessions", json={
            "client_session_id": "local-bg",
            "title": "Warsaw cars",
            "prompt_history": [],
            "resources": ["com"],
            "runs": [],
            "feedback": {},
            "batch_counter": 0,
        })
        self.assertEqual(created.status_code, 201)
        self.session = created.get_json()
        self.headers = {session_api.TOKEN_HEADER: self.session["session_token"]}

    def tearDown(self):
        self.job_patch.stop()
        self.session_patch.stop()

    def payload(self, **overrides):
        data = {
            "brief": "Сайт з продажу автомобілів у Варшаві",
            "resources": ["com"],
            "required_resources": ["com"],
            "preferences": {},
            "target_count": 500,
            "batch_size": 20,
        }
        data.update(overrides)
        return data

    def test_capabilities_never_expose_database_url(self):
        response = self.client.get("/api/background-search")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["enabled"])
        self.assertTrue(data["durable"])
        self.assertEqual(data["max_target"], 20000)
        self.assertNotIn("database_url", data)
        self.assertTrue(data["availability_hunter"]["supported"])
        self.assertEqual(data["availability_hunter"]["strict_match_policy"], "strict_all")
        self.assertFalse(data["availability_hunter"]["purchasable_is_strict_green"])
        self.assertFalse(data["availability_hunter"]["not_found_is_claimable"])
        self.assertIn("any_opportunity", data["availability_hunter"]["match_policies"])
        self.assertTrue(data["procedural_search"]["supported"])
        self.assertTrue(data["procedural_search"]["default_for_hunter"])
        self.assertTrue(data["procedural_search"]["one_root_at_a_time"])
        self.assertIn("phonetic", data["procedural_search"]["strategies"])
        self.assertTrue(data["turbo_search"]["supported"])
        self.assertFalse(data["turbo_search"]["primary_feed_strict_free_only"])
        self.assertEqual(data["turbo_search"]["default_match_policy"], "any_opportunity")
        self.assertTrue(data["turbo_search"]["all_checked_rows_remain_visible"])

    def test_create_list_read_and_cancel_job(self):
        path = f"/api/sessions/{self.session['session_id']}/search-jobs"
        created = self.client.post(path, json=self.payload(), headers=self.headers)
        self.assertEqual(created.status_code, 202)
        job = created.get_json()["job"]
        self.assertEqual(job["state"], "pending")
        self.assertEqual(job["target_count"], 500)

        listed = self.client.get(path, headers=self.headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.get_json()["jobs"][0]["id"], job["id"])

        detail = self.client.get(path + "/" + job["id"], headers=self.headers)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["job"]["run_id"], job["run_id"])

        cancelled = self.client.post(path + "/" + job["id"] + "/cancel", headers=self.headers)
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.get_json()["job"]["state"], "cancelled")

    def test_create_availability_hunter_defaults_to_procedural_result_search(self):
        path = f"/api/sessions/{self.session['session_id']}/search-jobs"
        created = self.client.post(
            path,
            json=self.payload(target_matches=3, max_checks=800),
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 202)
        job = created.get_json()["job"]
        self.assertEqual(job["target_count"], 800)
        hunter = job["search_context"]["availability_hunter"]
        self.assertTrue(hunter["enabled"])
        self.assertEqual(hunter["target_matches"], 3)
        self.assertEqual(hunter["max_checks"], 800)
        self.assertEqual(hunter["match_policy"], "strict_all")
        self.assertEqual(job["search_context"]["search_strategy"], "procedural")
        procedural = job["search_context"]["procedural_search"]
        self.assertTrue(procedural["enabled"])
        self.assertEqual(procedural["strategy"], "procedural")

    def test_create_turbo_hunter_keeps_broad_search_and_all_checked_rows(self):
        path = f"/api/sessions/{self.session['session_id']}/search-jobs"
        created = self.client.post(
            path,
            json=self.payload(target_matches=3, max_checks=500, search_strategy="turbo"),
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 202)
        job = created.get_json()["job"]
        context = job["search_context"]
        self.assertEqual(context["search_strategy"], "turbo")
        self.assertTrue(context["turbo_search"]["enabled"])
        self.assertFalse(context["turbo_search"]["strict_free_primary_feed"])
        self.assertTrue(context["turbo_search"]["all_checked_rows_visible"])
        self.assertEqual(context["turbo_search"]["match_policy"], "any_opportunity")
        self.assertEqual(context["availability_hunter"]["match_policy"], "any_opportunity")
        self.assertNotIn("procedural_search", context)
        self.assertIn("Turbo search", context["guidance"])

    def test_hunter_can_explicitly_keep_old_adaptive_strategy(self):
        path = f"/api/sessions/{self.session['session_id']}/search-jobs"
        created = self.client.post(
            path,
            json=self.payload(target_matches=2, max_checks=100, search_strategy="adaptive"),
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 202)
        job = created.get_json()["job"]
        self.assertIn("availability_hunter", job["search_context"])
        self.assertEqual(job["search_context"]["search_strategy"], "adaptive")
        self.assertNotIn("procedural_search", job["search_context"])
        self.assertNotIn("turbo_search", job["search_context"])

    def test_availability_hunter_bounds_and_strategy_are_enforced(self):
        path = f"/api/sessions/{self.session['session_id']}/search-jobs"
        bad_goal = self.client.post(
            path,
            json=self.payload(target_matches=0, max_checks=500),
            headers=self.headers,
        )
        self.assertEqual(bad_goal.status_code, 400)
        impossible = self.client.post(
            path,
            json=self.payload(target_matches=10, max_checks=5),
            headers=self.headers,
        )
        self.assertEqual(impossible.status_code, 400)
        too_large_budget = self.client.post(
            path,
            json=self.payload(target_matches=1, max_checks=20001),
            headers=self.headers,
        )
        self.assertEqual(too_large_budget.status_code, 400)
        invalid_strategy = self.client.post(
            path,
            json=self.payload(target_matches=1, max_checks=100, search_strategy="random-chaos"),
            headers=self.headers,
        )
        self.assertEqual(invalid_strategy.status_code, 400)

    def test_job_requires_capability_token(self):
        path = f"/api/sessions/{self.session['session_id']}/search-jobs"
        response = self.client.post(path, json=self.payload())
        self.assertEqual(response.status_code, 404)

    def test_target_and_batch_bounds_are_enforced(self):
        path = f"/api/sessions/{self.session['session_id']}/search-jobs"
        too_large = self.client.post(
            path,
            json=self.payload(target_count=20001),
            headers=self.headers,
        )
        self.assertEqual(too_large.status_code, 400)
        oversized_batch = self.client.post(
            path,
            json=self.payload(batch_size=21),
            headers=self.headers,
        )
        self.assertEqual(oversized_batch.status_code, 400)


if __name__ == "__main__":
    unittest.main()
