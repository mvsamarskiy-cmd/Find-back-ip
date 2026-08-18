import unittest

from background_jobs import SearchJobStore
from procedural_search import (
    MAX_STRATEGY_CHECKS,
    MIN_STRATEGY_CHECKS,
    STRATEGIES,
    prepare_procedural_context,
    record_procedural_batch,
)
from session_store import SessionStore


class ProceduralSearchR3Tests(unittest.TestCase):
    def setUp(self):
        self.session_store = SessionStore("sqlite+pysqlite:///:memory:")
        self.created = self.session_store.create_session({
            "client_session_id": "procedural-local",
            "title": "Containers",
            "prompt_history": [],
            "resources": ["telegram"],
            "shortlist": [],
            "direction_anchors": [],
            "runs": [],
            "feedback": {},
            "batch_counter": 0,
        })
        self.store = SearchJobStore(self.session_store)
        self.job = self.store.enqueue(
            self.created["id"],
            self.created["token"],
            {
                "prompt": "bottle jar vessel glass",
                "resources": ["telegram"],
                "required_resources": ["telegram"],
                "preferences": {},
                "search_context": {
                    "mode": "new_brand",
                    "procedural_search": {"enabled": True, "strategy": "procedural"},
                },
                "generation_context": {},
                "target_count": 500,
                "batch_size": 20,
                "max_batches": 75,
            },
        )

    @staticmethod
    def rows(count, status="taken"):
        return [
            {
                "name": f"Candidate{chr(65 + (index % 26))}{chr(65 + (index // 26))}",
                "availability": {"telegram": {"status": status}},
            }
            for index in range(count)
        ]

    def test_plan_uses_intelligence_roots_in_order(self):
        context, runtime = prepare_procedural_context(
            self.store,
            self.job,
            {},
            intelligence={"naming_roots": ["bottle", "jar", "vessel", "glass"]},
        )
        self.assertEqual(runtime["current_root"], "bottle")
        self.assertEqual(runtime["current_strategy"], STRATEGIES[0])
        self.assertEqual(context["procedural"]["focus_root"], "bottle")
        self.assertEqual(context["procedural"]["supporting_roots"][:2], ["jar", "vessel"])

    def test_high_collision_advances_strategy_but_stays_on_same_root(self):
        prepare_procedural_context(
            self.store,
            self.job,
            {},
            intelligence={"naming_roots": ["bottle", "jar", "vessel"]},
        )
        runtime = record_procedural_batch(
            self.store,
            self.job,
            self.rows(MIN_STRATEGY_CHECKS, "taken"),
        )
        self.assertEqual(runtime["current_root"], "bottle")
        self.assertEqual(runtime["current_strategy"], STRATEGIES[1])
        self.assertEqual(runtime["visited"][-1]["advance_reason"], "high_collision")
        self.assertGreaterEqual(runtime["visited"][-1]["collision_rate"], 0.8)

    def test_productive_strategy_gets_larger_sample_before_advancing(self):
        prepare_procedural_context(
            self.store,
            self.job,
            {},
            intelligence={"naming_roots": ["bottle", "jar"]},
        )
        first = record_procedural_batch(
            self.store,
            self.job,
            self.rows(MIN_STRATEGY_CHECKS, "not_found"),
        )
        self.assertEqual(first["current_strategy"], STRATEGIES[0])
        remaining = MAX_STRATEGY_CHECKS - MIN_STRATEGY_CHECKS
        second = record_procedural_batch(
            self.store,
            self.job,
            self.rows(remaining, "not_found"),
        )
        self.assertEqual(second["current_root"], "bottle")
        self.assertEqual(second["current_strategy"], STRATEGIES[1])
        self.assertEqual(second["visited"][-1]["advance_reason"], "strategy_budget")

    def test_root_changes_only_after_all_strategies_are_exhausted(self):
        prepare_procedural_context(
            self.store,
            self.job,
            {},
            intelligence={"naming_roots": ["bottle", "jar"]},
        )
        runtime = None
        for _strategy in STRATEGIES:
            runtime = record_procedural_batch(
                self.store,
                self.job,
                self.rows(MIN_STRATEGY_CHECKS, "taken"),
            )
        self.assertIsNotNone(runtime)
        self.assertEqual(runtime["current_root"], "jar")
        self.assertEqual(runtime["current_strategy"], STRATEGIES[0])
        self.assertEqual(len(runtime["visited"]), len(STRATEGIES))
        self.assertTrue(all(item["root"] == "bottle" for item in runtime["visited"]))

    def test_claimable_yield_is_counted_separately_from_conflicts(self):
        prepare_procedural_context(
            self.store,
            self.job,
            {},
            intelligence={"naming_roots": ["bottle", "jar"]},
        )
        rows = self.rows(10, "taken") + self.rows(5, "claimable") + self.rows(5, "not_found")
        runtime = record_procedural_batch(self.store, self.job, rows)
        self.assertEqual(runtime["strategy_checked"], 20)
        self.assertEqual(runtime["strategy_conflicts"], 10)
        self.assertEqual(runtime["strategy_matches"], 5)
        self.assertEqual(runtime["current_strategy"], STRATEGIES[0])


if __name__ == "__main__":
    unittest.main()
