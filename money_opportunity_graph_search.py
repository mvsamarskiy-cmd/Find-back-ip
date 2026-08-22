"""Money search wrapper that compiles Opportunity Graph v2.3."""
from __future__ import annotations

from money_opportunity_graph import attach_graph_to_payload, opportunity_graph_capabilities
from money_opportunity_search import money_opportunity_search_capabilities as base_capabilities
from money_opportunity_search import search_money_opportunities as base_search
from money_result_quality import apply_money_result_quality, money_result_quality_capabilities


MONEY_GRAPH_SEARCH_VERSION = "money-graph-search-v2.3"


def search_money_opportunities(*args, **kwargs):
    payload = base_search(*args, **kwargs)
    # Apply the final user-facing scope gate before building the graph. This keeps
    # a selected category as a requirement rather than allowing it to become
    # self-evidence, removes duplicate retrieval rows, and bounds mobile payloads.
    category = kwargs.get("category", "all")
    payload = apply_money_result_quality(payload, category=category)
    result = attach_graph_to_payload(payload)
    result["intelligence_version"] = MONEY_GRAPH_SEARCH_VERSION
    return result


def money_opportunity_search_capabilities() -> dict:
    payload = dict(base_capabilities())
    payload["version"] = MONEY_GRAPH_SEARCH_VERSION
    payload["opportunity_graph"] = opportunity_graph_capabilities()
    payload["result_quality"] = money_result_quality_capabilities()
    payload["truth_semantics"] = "money_candidate_search_plus_evidence_graph_not_legal_identity_or_compatibility_proof"
    return payload


__all__ = ["MONEY_GRAPH_SEARCH_VERSION", "money_opportunity_search_capabilities", "search_money_opportunities"]
