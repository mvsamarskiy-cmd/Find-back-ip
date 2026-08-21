import unittest
from unittest.mock import patch

from money_opportunity_graph import attach_graph_to_payload, build_opportunity_graph
from money_opportunity_graph_search import search_money_opportunities


class OpportunityGraphTests(unittest.TestCase):
    def record(self, title, *, opportunity_id, urls=None, counterparty="PARP", description="", deadline="2026-12-31"):
        return {
            "opportunity_id": opportunity_id,
            "title": title,
            "description": description,
            "opportunity_type": "grant",
            "family": "funding",
            "funder_or_counterparty": counterparty,
            "source_urls": urls or [],
            "status": "open",
            "deadline": deadline,
            "current_call_verified": False,
            "eligibility_state": "possible",
            "practical_ranking": {"score": 70},
            "retrieval": {"transport": "web"},
        }

    def test_one_call_with_two_urls_creates_two_source_observations(self):
        record = self.record(
            "Green Innovation Call 2026",
            opportunity_id="mo_green",
            urls=[
                "https://parp.gov.pl/call/green?utm_source=x",
                "https://funduszeeuropejskie.gov.pl/green/",
            ],
        )
        graph = build_opportunity_graph([record])
        types = [node["type"] for node in graph["nodes"]]
        self.assertEqual(types.count("call"), 1)
        self.assertEqual(types.count("source_observation"), 2)
        observed = [edge for edge in graph["edges"] if edge["relation"] == "observed_at"]
        self.assertEqual(len(observed), 2)
        urls = {node["url"] for node in graph["nodes"] if node["type"] == "source_observation"}
        self.assertIn("https://parp.gov.pl/call/green", urls)

    def test_organization_label_is_deduplicated_across_calls(self):
        records = [
            self.record("Innovation Programme Round A", opportunity_id="mo_a", urls=["https://parp.gov.pl/a"]),
            self.record("Export Programme Round B", opportunity_id="mo_b", urls=["https://parp.gov.pl/b"]),
        ]
        graph = build_opportunity_graph(records)
        orgs = [node for node in graph["nodes"] if node["type"] == "organization"]
        self.assertEqual(len(orgs), 1)
        offered = [edge for edge in graph["edges"] if edge["relation"] == "offered_by_observed_counterparty"]
        self.assertEqual(len(offered), 2)
        self.assertEqual({edge["target"] for edge in offered}, {orgs[0]["id"]})
        self.assertEqual(orgs[0]["identity_state"], "observed_label_not_legal_entity_verified")

    def test_shared_explicit_reference_creates_candidate_not_identity_fact(self):
        records = [
            self.record("Innovation Funding", opportunity_id="mo_a", urls=["https://a.example/x"], description="Call ID EIC-2026-01. Open for SMEs."),
            self.record("EIC opportunity", opportunity_id="mo_b", urls=["https://b.example/y"], description="Reference ID EIC-2026-01. Deadline soon."),
        ]
        graph = build_opportunity_graph(records)
        same = [edge for edge in graph["edges"] if edge["relation"] == "same_call_candidate"]
        self.assertEqual(len(same), 1)
        self.assertGreaterEqual(same[0]["confidence"], 0.9)
        self.assertIn("candidate", same[0]["state"])
        self.assertIn("EIC-2026-01", " ".join(same[0]["evidence"]))
        self.assertIn("candidate_identity_not_fact", graph["truth_semantics"]["same_call_candidate"])

    def test_title_similarity_only_creates_same_program_candidate(self):
        records = [
            self.record("Green Innovation Programme 2026 Round 1", opportunity_id="mo_a", urls=["https://a.example/1"]),
            self.record("Green Innovation Programme 2027 Round 2", opportunity_id="mo_b", urls=["https://a.example/2"]),
        ]
        graph = build_opportunity_graph(records)
        relations = [edge["relation"] for edge in graph["edges"]]
        self.assertIn("same_program_candidate", relations)
        self.assertNotIn("same_call", relations)

    def test_constraints_are_nodes_but_pairwise_compatibility_is_not_inferred(self):
        record = self.record(
            "SME grant",
            opportunity_id="mo_a",
            urls=["https://parp.gov.pl/a"],
            description="This support is de minimis aid. Double financing of the same costs is not allowed.",
        )
        graph = build_opportunity_graph([record])
        kinds = {node.get("kind") for node in graph["nodes"] if node["type"] == "constraint"}
        self.assertIn("de_minimis", kinds)
        self.assertIn("double_financing_restriction", kinds)
        self.assertEqual(graph["combination_analysis"]["confirmed_combinations"], 0)
        self.assertEqual(graph["combination_analysis"]["confirmed_conflicts"], 0)
        self.assertEqual(graph["combination_analysis"]["state"], "not_inferred_without_rule_evidence")

    def test_attach_graph_adds_call_reference_to_money_record(self):
        payload = {"money_records": [self.record("Grant A", opportunity_id="mo_a", urls=["https://example.org/a"])]}
        result = attach_graph_to_payload(payload)
        self.assertIn("opportunity_graph", result)
        self.assertTrue(result["money_records"][0]["graph_call_id"].startswith("call_"))


class OpportunityGraphSearchWrapperTests(unittest.TestCase):
    def test_wrapper_preserves_money_payload_and_adds_graph(self):
        base = {
            "money_records": [{
                "opportunity_id": "mo_a", "title": "Grant A", "description": "",
                "opportunity_type": "grant", "family": "funding", "funder_or_counterparty": "Agency",
                "source_urls": ["https://example.org/a"], "status": "open", "deadline": None,
                "practical_ranking": {"score": 50}, "retrieval": {"transport": "web"},
            }],
            "results": [],
        }
        with patch("money_opportunity_graph_search.base_search", return_value=base):
            result = search_money_opportunities("find grants")
        self.assertEqual(result["intelligence_version"], "money-graph-search-v2.3")
        self.assertEqual(result["opportunity_graph"]["summary"]["by_type"]["call"], 1)


if __name__ == "__main__":
    unittest.main()
