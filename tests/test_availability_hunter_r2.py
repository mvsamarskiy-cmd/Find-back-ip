import unittest

from availability_hunter import (
    count_persisted_matches,
    row_is_strict_match,
    run_availability_hunter_job,
)
from background_jobs import SearchJobStore
from session_store import SessionStore


class AvailabilityHunterR2Tests(unittest.TestCase):
    def setUp(self):
        self.session_store = SessionStore("sqlite+pysqlite:///:memory:")
        self.created = self.session_store.create_session({
            "client_session_id": "hunter-local",
            "title": "Hunter",
            "prompt_history": [],
            "resources": ["telegram"],
            "shortlist": [],
            "direction_anchors": [],
            "runs": [],
            "feedback": {},
            "batch_counter": 0,
        })
        self.jobs = SearchJobStore(self.session_store)

    def enqueue_hunter(self, *, target_matches=2, max_checks=8, batch_size=2, max_batches=10):
        return self.jobs.enqueue(
            self.created["id"],
            self.created["token"],
            {
                "prompt": "find free telegram handles",
                "resources": ["telegram"],
                "required_resources": ["telegram"],
                "preferences": {},
                "search_context": {
                    "mode": "new_brand",
                    "availability_hunter": {
                        "enabled": True,
                        "target_matches": target_matches,
                        "max_checks": max_checks,
                        "match_policy": "claimable",
                    },
                },
                "generation_context": {},
                "target_count": max_checks,
                "batch_size": batch_size,
                "max_batches": max_batches,
            },
        )

    @staticmethod
    def verified(candidate, status):
        row = dict(candidate)
        row["availability"] = {
            "telegram": {
                "status": status,
                "detail": "fixture",
                "source": "fixture",
                "method": "fixture",
                "confidence": 1.0,
                "claimability": "confirmed" if status == "claimable" else "unconfirmed",
            }
        }
        row["verification"] = {}
        row["bundle_state"] = "confirmed" if status == "claimable" else "promising"
        row["bundle_score"] = 100 if status == "claimable" else 50
        row["checked"] = True
        return row

    def test_strict_match_requires_claimable_on_every_required_resource(self):
        self.assertTrue(row_is_strict_match(
            {"availability": {"telegram": {"status": "claimable"}}},
            ["telegram"],
        ))
        self.assertFalse(row_is_strict_match(
            {"availability": {"telegram": {"status": "not_found"}}},
            ["telegram"],
        ))
        self.assertFalse(row_is_strict_match(
            {"availability": {"telegram": {"status": "purchasable"}}},
            ["telegram"],
        ))

    def test_hunter_stops_when_strict_match_target_is_reached(self):
        job = self.enqueue_hunter(target_matches=2, max_checks=8, batch_size=2)
        batches = []

        def generate(_job, _count, context):
            batches.append(context)
            index = len(batches)
            return [
                {"name": f"Free{index}A"},
                {"name": f"Taken{index}B"},
            ]

        def verify(_job, candidate):
            status = "claimable" if candidate["name"].startswith("Free") else "taken"
            return self.verified(candidate, status)

        result = run_availability_hunter_job(
            self.jobs, "hunter-worker", generate, verify, verify_workers=1
        )
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["stop_reason"], "target_matches_reached")
        self.assertEqual(result["delivered_count"], 4)
        runtime = (result["preferences"] or {}).get("_hunter_runtime") or {}
        self.assertEqual(runtime["matches"], 2)
        self.assertEqual(runtime["target_matches"], 2)
        self.assertEqual(runtime["checked"], 4)
        self.assertEqual(count_persisted_matches(self.jobs, result), 2)
        self.assertEqual(batches[-1]["availability_hunter"]["current_matches"], 1)

    def test_purchasable_does_not_satisfy_free_match_goal(self):
        self.enqueue_hunter(target_matches=1, max_checks=2, batch_size=1, max_batches=2)
        counter = {"value": 0}

        def generate(_job, _count, _context):
            counter["value"] += 1
            return [{"name": f"Market{counter['value']}"}]

        def verify(_job, candidate):
            return self.verified(candidate, "purchasable")

        result = run_availability_hunter_job(
            self.jobs, "hunter-market", generate, verify, verify_workers=1
        )
        self.assertEqual(result["stop_reason"], "search_budget_exhausted")
        runtime = (result["preferences"] or {}).get("_hunter_runtime") or {}
        self.assertEqual(runtime["matches"], 0)
        self.assertEqual(result["delivered_count"], 2)

    def test_hunter_stops_at_check_budget_when_no_match_exists(self):
        self.enqueue_hunter(target_matches=2, max_checks=3, batch_size=2, max_batches=4)
        counter = {"value": 0}

        def generate(_job, count, _context):
            rows = []
            for _ in range(count):
                counter["value"] += 1
                rows.append({"name": f"Taken{counter['value']}"})
            return rows

        def verify(_job, candidate):
            return self.verified(candidate, "taken")

        result = run_availability_hunter_job(
            self.jobs, "hunter-budget", generate, verify, verify_workers=1
        )
        self.assertEqual(result["stop_reason"], "search_budget_exhausted")
        self.assertEqual(result["delivered_count"], 3)
        runtime = (result["preferences"] or {}).get("_hunter_runtime") or {}
        self.assertEqual(runtime["checked"], 3)
        self.assertEqual(runtime["matches"], 0)

    def test_legacy_job_keeps_legacy_target_semantics(self):
        self.jobs.enqueue(
            self.created["id"],
            self.created["token"],
            {
                "prompt": "legacy",
                "resources": ["telegram"],
                "required_resources": ["telegram"],
                "preferences": {},
                "search_context": {"mode": "new_brand"},
                "generation_context": {},
                "target_count": 2,
                "batch_size": 2,
                "max_batches": 2,
            },
        )

        def generate(_job, _count, _context):
            return [{"name": "LegacyOne"}, {"name": "LegacyTwo"}]

        def verify(_job, candidate):
            return self.verified(candidate, "taken")

        result = run_availability_hunter_job(
            self.jobs, "legacy-worker", generate, verify, verify_workers=1
        )
        self.assertEqual(result["stop_reason"], "target_reached")
        self.assertEqual(result["delivered_count"], 2)


if __name__ == "__main__":
    unittest.main()
