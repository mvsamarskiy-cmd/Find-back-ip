import unittest

from candidate_funnel import structural_quality as legacy_structural_quality
from final_ranking import (
    annotate_candidate,
    availability_metrics,
    final_ranking_sort_key,
    name_quality_score,
    rank_candidate_pool_v2,
    strict_availability_state,
    structural_quality_score,
)


class FinalRankingTests(unittest.TestCase):
    def test_camelcase_compound_is_not_penalized_by_fake_boundary_cluster(self):
        legacy = legacy_structural_quality("DawnFlock")
        improved = structural_quality_score("DawnFlock")
        self.assertGreater(improved, legacy)
        self.assertGreater(name_quality_score("DawnFlock"), name_quality_score("Nvrtsk"))

    def test_ranker_exposes_independent_quality_dimensions(self):
        rows = rank_candidate_pool_v2([
            {"name": "DawnFlock", "family": "semantic_compound"},
            {"name": "Nvrtsk", "family": "invented_phonetic"},
        ])
        self.assertEqual(rows[0]["name"], "DawnFlock")
        for field in (
            "structural_quality_score",
            "linguistic_quality_score",
            "name_quality_score",
            "local_quality_score",
        ):
            self.assertIn(field, rows[0])

    def test_free_paid_absence_and_conflicts_stay_distinct(self):
        self.assertEqual(
            strict_availability_state({"com": {"status": "claimable"}}, ["com"]),
            "claimable",
        )
        self.assertEqual(
            strict_availability_state({
                "com": {"status": "claimable"},
                "telegram": {"status": "purchasable"},
            }, ["com", "telegram"]),
            "purchasable",
        )
        self.assertEqual(
            strict_availability_state({
                "com": {"status": "claimable"},
                "telegram": {"status": "not_found"},
            }, ["com", "telegram"]),
            "promising",
        )
        self.assertEqual(
            strict_availability_state({"com": {"status": "taken"}}, ["com"]),
            "conflict",
        )
        self.assertEqual(
            strict_availability_state({"com": {"status": "unknown"}}, ["com"]),
            "unresolved",
        )

    def test_evidence_confidence_is_not_availability_opportunity(self):
        row = {
            "availability": {"com": {"status": "taken", "confidence": 1.0}},
            "required_resources": ["com"],
        }
        metrics = availability_metrics(row)
        self.assertEqual(metrics["availability_state"], "conflict")
        self.assertEqual(metrics["availability_evidence_confidence_score"], 100.0)
        self.assertEqual(metrics["availability_opportunity_score"], 0.0)

    def test_final_score_keeps_naming_dominant_but_penalizes_real_conflict(self):
        base = {
            "name": "DawnFlock",
            "family": "semantic_compound",
            "user_fit_score": 82.0,
            "adaptive_relevance_score": 86.0,
            "required_resources": ["com"],
        }
        free = dict(base)
        free["availability"] = {"com": {"status": "claimable", "confidence": 1.0}}
        blocked = dict(base)
        blocked["availability"] = {"com": {"status": "taken", "confidence": 1.0}}

        free_rank = annotate_candidate(free)
        blocked_rank = annotate_candidate(blocked)
        self.assertEqual(free_rank["availability_state"], "claimable")
        self.assertEqual(blocked_rank["availability_state"], "conflict")
        self.assertGreater(free_rank["final_score"], blocked_rank["final_score"])
        self.assertEqual(free_rank["name_quality_score"], blocked_rank["name_quality_score"])
        self.assertEqual(free_rank["user_fit_score"], blocked_rank["user_fit_score"])

    def test_not_found_never_becomes_free_through_ranking(self):
        row = {
            "name": "SkyFlock",
            "user_fit_score": 90,
            "availability": {"com": {"status": "not_found", "confidence": 1.0}},
            "required_resources": ["com"],
        }
        ranking = annotate_candidate(row)
        self.assertEqual(ranking["availability_state"], "promising")
        self.assertNotIn("вільність підтверджена", ranking["ranking_reason"])

    def test_sort_key_attaches_transparent_breakdown(self):
        row = {
            "name": "RiverWing",
            "user_fit_score": 75,
            "availability": {"com": {"status": "claimable", "confidence": 0.9}},
            "required_resources": ["com"],
        }
        final_ranking_sort_key(row)
        self.assertEqual(row["ranking_model"], "final-v1")
        self.assertIn("final_score", row)
        self.assertIn("name_quality_score", row)
        self.assertIn("availability_opportunity_score", row)
        self.assertIn("availability_evidence_confidence_score", row)
        self.assertIn("ranking_reason", row)


class FinalRankingRuntimeTests(unittest.TestCase):
    def test_production_bootstrap_exposes_ranking_contract(self):
        from telegram_bootstrap import app

        diagnostics = app.test_client().get("/api/verification/diagnostics").get_json()
        contract = diagnostics["final_ranking"]
        self.assertTrue(contract["enabled"])
        self.assertEqual(contract["model"], "final-v1")
        self.assertEqual(contract["strict_free_state"], "claimable")
        self.assertEqual(contract["paid_state"], "purchasable")
        self.assertFalse(contract["availability_can_rewrite_semantic_truth"])

    def test_runtime_bundle_adds_strict_paid_vs_free_state(self):
        import app as app_module
        from telegram_bootstrap import app  # noqa: F401 - installs wrappers

        free = app_module.classify_identity_bundle(
            {"com": {"status": "claimable"}}, ["com"]
        )
        paid = app_module.classify_identity_bundle(
            {
                "com": {"status": "claimable"},
                "telegram": {"status": "purchasable"},
            },
            ["com", "telegram"],
        )
        self.assertEqual(free["bundle_availability_state"], "claimable")
        self.assertEqual(paid["bundle_availability_state"], "purchasable")
        # Legacy bundle_state remains for compatibility, but the new field is the
        # semantic source of truth for free-vs-paid decisions.
        self.assertIn("bundle_state", paid)
        self.assertEqual(paid["bundle_purchasable"], ["telegram"])


if __name__ == "__main__":
    unittest.main()
