"""Universal Search v5 with Money / Material Opportunity Intelligence + Opportunity Graph."""
from __future__ import annotations

import requests

import universal_search_entity as entity_search
from money_opportunity_graph_search import money_opportunity_search_capabilities, search_money_opportunities


def search_universal(
    query,
    *,
    category="all",
    country="EU",
    requester=requests.get,
    poster=requests.post,
    opportunity_searcher=None,
    general_searcher=None,
    module_searcher=None,
    multi_searcher=None,
    synthesizer=None,
):
    kwargs = {
        "category": category,
        "country": country,
        "requester": requester,
        "poster": poster,
        "opportunity_searcher": opportunity_searcher or search_money_opportunities,
    }
    if general_searcher is not None:
        kwargs["general_searcher"] = general_searcher
    if module_searcher is not None:
        kwargs["module_searcher"] = module_searcher
    if multi_searcher is not None:
        kwargs["multi_searcher"] = multi_searcher
    if synthesizer is not None:
        kwargs["synthesizer"] = synthesizer
    return entity_search.search_universal(query, **kwargs)


def universal_search_capabilities() -> dict:
    payload = dict(entity_search.universal_search_capabilities())
    money = money_opportunity_search_capabilities()
    payload["opportunity_transport"] = {
        "version": "tor-opportunity-retrieval-v1",
        "enabled_by_default": True,
        "exact_query_max_calls": 1,
        "onion_service_evidence": True,
        "onion_location_discovery": True,
        "verification_inferred_from_tor": False,
        "money_v2_planner": True,
    }
    payload["money_opportunity"] = money
    payload["retrieval_transport_version"] = "tor-opportunity-transport-v1"
    return payload


__all__ = ["search_universal", "universal_search_capabilities"]
