"""Opportunity-aware wrapper around the existing private global search engine."""
from __future__ import annotations

import re

import requests

from global_search import global_search_capabilities, search_global as _search_global
from opportunity_intelligence import enrich_payload


INTENT_PATTERNS = {
    "grant": (
        r"\bgrants?\b", r"\bdotacj\w*\b", r"\bdofinansowan\w*\b", r"\bгрант\w*\b",
    ),
    "challenge": (
        r"\bchallenges?\b", r"\bprizes?\b", r"\bcompetition\b", r"\bkonkurs\w*\b",
        r"\bконкурс\w*\b", r"\bприз\w*\b",
    ),
    "funding": (
        r"\bfunding\b", r"\binvestment\b", r"\baccelerator\w*\b", r"\bfinansowan\w*\b",
        r"\bінвест\w*\b", r"\bфінансув\w*\b",
    ),
    "business_aid": (
        r"\bbusiness aid\b", r"\bsme support\b", r"\bpomoc dla firm\b", r"\bwsparcie dla firm\b",
        r"\bдопомог\w* бізнес\w*\b", r"\bпідтримк\w* бізнес\w*\b",
    ),
    "research": (
        r"\bresearch call\b", r"\bhorizon\b", r"\bresearch funding\b", r"\bbadawcz\w*\b",
        r"\bдослід\w*\b", r"\bнауков\w*\b",
    ),
}


def infer_query_category(query):
    """Infer one high-confidence opportunity vertical from natural language."""
    text = " ".join(str(query or "").split()).casefold()
    scores = {}
    for category, patterns in INTENT_PATTERNS.items():
        score = sum(1 for pattern in patterns if re.search(pattern, text, flags=re.I))
        if score:
            scores[category] = score
    if not scores:
        return "all"
    return sorted(scores, key=lambda category: (-scores[category], list(INTENT_PATTERNS).index(category)))[0]


def search_global(query, *, category="all", country="EU", requester=requests.get, poster=requests.post):
    requested_category = str(category or "all").strip().lower()
    routed_category = infer_query_category(query) if requested_category == "all" else requested_category
    payload = _search_global(
        query,
        category=routed_category,
        country=country,
        requester=requester,
        poster=poster,
    )
    enriched = enrich_payload(payload, query=query, country=country, requester=requester)
    enriched["requested_category"] = requested_category
    enriched["routed_category"] = routed_category
    enriched["intent_routed"] = requested_category == "all" and routed_category != "all"
    return enriched


def opportunity_search_capabilities():
    payload = dict(global_search_capabilities())
    payload.update({
        "intelligence_version": "opportunity-v1",
        "normalized_fields": ["amount", "deadline", "status", "eligibility", "verification", "fit"],
        "priority_scope": ["PL", "EU"],
        "priority_categories": ["grant", "challenge", "funding", "business_aid", "research"],
        "deep_source_verification": True,
        "natural_language_intent_routing": True,
    })
    return payload


__all__ = ["infer_query_category", "opportunity_search_capabilities", "search_global"]
