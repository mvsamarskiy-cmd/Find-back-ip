"""Opportunity-aware wrapper around the existing private global search engine."""
from __future__ import annotations

import requests

from global_search import global_search_capabilities, search_global as _search_global
from opportunity_intelligence import enrich_payload


def search_global(query, *, category="all", country="EU", requester=requests.get, poster=requests.post):
    payload = _search_global(
        query,
        category=category,
        country=country,
        requester=requester,
        poster=poster,
    )
    return enrich_payload(payload, query=query, country=country, requester=requester)


def opportunity_search_capabilities():
    payload = dict(global_search_capabilities())
    payload.update({
        "intelligence_version": "opportunity-v1",
        "normalized_fields": ["amount", "deadline", "status", "eligibility", "verification", "fit"],
        "priority_scope": ["PL", "EU"],
        "priority_categories": ["grant", "challenge", "funding", "business_aid", "research"],
        "deep_source_verification": True,
    })
    return payload


__all__ = ["opportunity_search_capabilities", "search_global"]
