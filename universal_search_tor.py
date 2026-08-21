"""Universal Search v5 with an additive Tor lane for Opportunity Intelligence."""
from __future__ import annotations

import requests

import universal_search_entity as entity_search
from opportunity_tor_search import opportunity_search_capabilities, search_global as search_opportunity_with_tor


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
        "opportunity_searcher": opportunity_searcher or search_opportunity_with_tor,
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
    payload["opportunity_transport"] = opportunity_search_capabilities().get("tor_retrieval")
    payload["retrieval_transport_version"] = "tor-opportunity-transport-v1"
    return payload


__all__ = ["search_universal", "universal_search_capabilities"]
