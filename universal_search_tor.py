"""Universal Search v5 with Money / Material Opportunity Intelligence v2."""
from __future__ import annotations

import requests

import universal_search_entity as entity_search
from money_opportunity_search import money_opportunity_search_capabilities, search_money_opportunities


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
        "tor_retrieval": money.get("tor_exact_query_max_calls"),
        "exact_query_first": money.get("standard_exact_query_first"),
        "truth_semantics": money.get("truth_semantics"),
    }
    payload["money_opportunity"] = money
    payload["retrieval_transport_version"] = "money-opportunity-v2+tor"
    return payload


__all__ = ["search_universal", "universal_search_capabilities"]
