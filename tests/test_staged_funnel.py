import unittest

from candidate_funnel import (
    LOCAL_SOURCE,
    linguistic_quality,
    staged_candidate_pool,
)


class StagedFunnelTests(unittest.TestCase):
    def test_readability_proxy_penalizes_mechanical_clusters(self):
        self.assertGreater(linguistic_quality("Navero"), linguistic_quality("Nvrtqsk"))
        self.assertGreater(linguistic_quality("Lumena"), linguistic_quality("Luuuuumena"))

    def test_staged_pool_reduces_large_local_space_before_external_shortlist(self):
        brief = "citrus lemon lime fresh energy sun yellow spark bright juice flavor"
        rows, metrics = staged_candidate_pool(
            [],
            brief,
            local_limit=1200,
            structural_limit=180,
            linguistic_limit=80,
            collision_limit=30,
        )
        self.assertGreater(metrics["raw_unique"], 200)
        self.assertEqual(metrics["structural_survivors"], 180)
        self.assertEqual(metrics["linguistic_survivors"], 80)
        self.assertLessEqual(metrics["collision_survivors"], 30)
        self.assertEqual(len(rows), metrics["collision_survivors"])
        self.assertTrue(all(row["candidate_source"] == LOCAL_SOURCE for row in rows))
        self.assertTrue(all("local_quality_score" in row for row in rows))
        self.assertTrue(all("linguistic_quality_score" in row for row in rows))
        self.assertTrue(all("funnel_score" in row for row in rows))

    def test_model_candidates_share_the_same_staged_gate(self):
        model = [{
            "name": "Navero",
            "family": "abstract",
            "reason": "model",
            "pronunciation": "na-ve-ro",
            "language_risks": [],
        }]
        rows, metrics = staged_candidate_pool(
            model,
            "citrus lemon lime fresh energy sun",
            local_limit=300,
            structural_limit=100,
            linguistic_limit=50,
            collision_limit=20,
        )
        self.assertEqual(metrics["model_candidates"], 1)
        self.assertGreater(metrics["local_candidates"], 0)
        self.assertTrue(any(row["name"] == "Navero" for row in rows))

    def test_stage_limits_are_hard_caps(self):
        rows, metrics = staged_candidate_pool(
            [],
            "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda",
            local_limit=700,
            structural_limit=90,
            linguistic_limit=40,
            collision_limit=15,
        )
        self.assertLessEqual(metrics["local_candidates"], 700)
        self.assertLessEqual(metrics["structural_survivors"], 90)
        self.assertLessEqual(metrics["linguistic_survivors"], 40)
        self.assertLessEqual(len(rows), 15)


if __name__ == "__main__":
    unittest.main()
