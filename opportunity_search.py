"""Opportunity-aware wrapper around the existing private global search engine."""
from __future__ import annotations

import re

import requests

from global_search import global_search_capabilities, search_global as _search_global
from money_taxonomy import looks_like_material_opportunity
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

BROAD_MONEY_OPPORTUNITY_PATTERNS = (
    r"\b(?:money|financial|material) opportunit\w*\b",
    r"\bwhere (?:is|are) the money\b",
    r"\bmożliwoś\w* (?:finansow\w*|zarobk\w*|biznesow\w*)\b",
    r"\bgdzie (?:są|sa) pieni[aą]dze\b",
    r"\b(?:матеріальн|фінансов|грошов)\w* можливост\w*\b",
    r"\bде (?:є|знайти) грош\w*\b",
    r"\bусі можливост\w*.*(?:грош|зароб|фінанс)\w*\b",
    # A business constrained by zero/no upfront capital is a material-opportunity
    # request, not a generic web lookup. Keep these patterns deliberately narrow:
    # the word "business" alone must not hijack ordinary research queries.
    r"\bбізнес\w*\b.*(?:\bза\s*0\b|\bз\s+нуля\b|\bбез\s+(?:вклад\w*|капітал\w*|інвестиц\w*))",
    r"(?:\bзнайд\w*|\bшука\w*)[^\n]{0,120}\bбізнес\w*\b[^\n]{0,80}\b0\s*(?:злот\w*|грив\w*|євро|долар\w*)\b",
    r"\bbiznes\w*\b.*(?:\bza\s*0\b|\bod\s+zera\b|\bbez\s+(?:wk[łl]adu|kapita[łl]u|inwestycj\w*))",
    r"\bbusiness\w*\b.*(?:\bfor\s*0\b|\bfrom\s+zero\b|\bzero\s+(?:capital|budget)\b|\bno\s+upfront\s+(?:capital|investment)\b|\bwithout\s+(?:capital|investment)\b)",
)


def infer_query_category(query):
    """Infer one high-confidence opportunity vertical from natural language.

    Legacy categories stay stable. Actionable money/material needs that do not
    name a legacy mechanism are routed as ``material`` so the universal router
    can select the broader Money Opportunity v2 lane without mislabelling them.
    """
    text = " ".join(str(query or "").split()).casefold()
    scores = {}
    for category, patterns in INTENT_PATTERNS.items():
        score = sum(1 for pattern in patterns if re.search(pattern, text, flags=re.I))
        if score:
            scores[category] = score
    if scores:
        return sorted(scores, key=lambda category: (-scores[category], list(INTENT_PATTERNS).index(category)))[0]
    if any(re.search(pattern, text, flags=re.I) for pattern in BROAD_MONEY_OPPORTUNITY_PATTERNS):
        return "material"
    if looks_like_material_opportunity(query):
        return "material"
    return "all"


def search_global(query, *, category="all", country="EU", requester=requests.get, poster=requests.post):
    requested_category = str(category or "all").strip().lower()
    routed_category = infer_query_category(query) if requested_category == "all" else requested_category
    base_category = "all" if routed_category == "material" else routed_category
    payload = _search_global(
        query,
        category=base_category,
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
        "intelligence_version": "opportunity-v1+material-router-v2",
        "normalized_fields": ["amount", "deadline", "status", "eligibility", "verification", "fit"],
        "priority_scope": ["PL", "EU"],
        "priority_categories": ["grant", "challenge", "funding", "business_aid", "research", "material"],
        "deep_source_verification": True,
        "natural_language_intent_routing": True,
        "material_opportunity_router": True,
        "zero_capital_business_routing": True,
    })
    return payload


__all__ = ["infer_query_category", "opportunity_search_capabilities", "search_global"]
