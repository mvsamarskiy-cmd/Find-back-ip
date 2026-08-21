"""Universal intelligence router for NameMachine private Global Search.

The router keeps opportunity-specific interpretation opt-in/high-confidence.
Queries that do not match an opportunity vertical use a neutral web-retrieval
path with no forced EU geography, grant vocabulary, or opportunity source sites.
"""
from __future__ import annotations

import re

import requests

import global_search as base_search
from opportunity_search import (
    infer_query_category,
    opportunity_search_capabilities,
    search_global as search_opportunity,
)


AMBIGUOUS_OPPORTUNITY_CATEGORIES = {"funding", "challenge"}
OPPORTUNITY_CONTEXT_PATTERNS = (
    r"\bapply\w*\b", r"\bapplication\w*\b", r"\bopen call\b", r"\bdeadline\b",
    r"\bstartup\w*\b", r"\bsme\b", r"\bprize\w*\b", r"\bgrant\w*\b",
    r"\bopportunit\w*\b", r"\bfind\b", r"\bavailable\b",
    r"\bподат\w*\b", r"\bзаявк\w*\b", r"\bдедлайн\w*\b", r"\bстартап\w*\b",
    r"\bприз\w*\b", r"\bможливост\w*\b", r"\bзнайд\w*\b", r"\bвідкрит\w*\b",
    r"\bwniosk\w*\b", r"\bnab[oó]r\w*\b", r"\btermin\w*\b", r"\bstartup\w*\b",
    r"\bnagrod\w*\b", r"\bmożliwoś\w*\b", r"\bznajd\w*\b", r"\botwart\w*\b",
)


GENERAL_INTENT_PATTERNS = {
    "current": (
        r"\blatest\b", r"\btoday\b", r"\bcurrent\b", r"\brecent\b", r"\bnews\b",
        r"\bсьогодні\b", r"\bзараз\b", r"\bостанні\w*\b", r"\bновин\w*\b",
        r"\bdzisiaj\b", r"\bteraz\b", r"\bnajnowsz\w*\b", r"\baktualn\w*\b",
    ),
    "comparison": (
        r"\bcompare\b", r"\bversus\b", r"\bvs\.?\b",
        r"\bпорівня\w*\b", r"\bпорівняй\b", r"\bпроти\b",
        r"\bporówn\w*\b", r"\bversus\b",
    ),
    "how_to": (
        r"\bhow to\b", r"\bhow do i\b",
        r"\bяк\s+(?:зробити|знайти|отримати|налаштувати|працює)\b",
        r"\bjak\s+(?:zrobić|znaleźć|uzyskać|ustawić|działa)\b",
    ),
}


def infer_general_intent(query: object) -> str:
    """Return a coarse, auditable research shape for generic web retrieval."""
    text = " ".join(str(query or "").split()).casefold()
    scores = {}
    for intent, patterns in GENERAL_INTENT_PATTERNS.items():
        hits = sum(1 for pattern in patterns if re.search(pattern, text, flags=re.I))
        if hits:
            scores[intent] = hits
    if not scores:
        return "general"
    order = list(GENERAL_INTENT_PATTERNS)
    return sorted(scores, key=lambda name: (-scores[name], order.index(name)))[0]


def classify_search_route(query: object, *, category: object = "all") -> dict:
    """Choose a specialized opportunity lane only when evidence justifies it."""
    requested = str(category or "all").strip().lower().replace("-", "_")
    if requested != "all":
        return {
            "route": "opportunity",
            "reason": "explicit_category",
            "requested_category": requested,
            "routed_category": requested,
            "general_intent": None,
        }

    inferred = infer_query_category(query)
    text = " ".join(str(query or "").split()).casefold()
    has_context = any(
        re.search(pattern, text, flags=re.I)
        for pattern in OPPORTUNITY_CONTEXT_PATTERNS
    )
    if inferred != "all" and (
        inferred not in AMBIGUOUS_OPPORTUNITY_CATEGORIES or has_context
    ):
        return {
            "route": "opportunity",
            "reason": "high_confidence_opportunity_intent",
            "requested_category": "all",
            "routed_category": inferred,
            "general_intent": None,
        }

    return {
        "route": "general_web",
        "reason": "no_specialized_intent",
        "requested_category": "all",
        "routed_category": "all",
        "general_intent": infer_general_intent(query),
    }


def _general_score(title: str, description: str, query: str, provider_rank: int) -> int:
    text = f"{title} {description}".casefold()
    tokens = base_search._query_tokens(query)
    token_hits = sum(1 for token in tokens if token in text)
    score = max(0, 55 - min(provider_rank, 35))
    score += min(35, token_hits * 7)
    return max(0, min(100, score))


def _decorate_general_rows(raw_rows, query, collected, seen):
    for provider_rank, raw in enumerate(raw_rows if isinstance(raw_rows, list) else []):
        if not isinstance(raw, dict):
            continue
        title = base_search._clean_text(raw.get("title"), 300)
        description = base_search._clean_text(raw.get("description"), 900)
        url = base_search._clean_text(raw.get("url"), 1000)
        canonical = base_search._canonical_url(url)
        if not title or not canonical or canonical in seen:
            continue
        seen.add(canonical)
        host = base_search._host(url)
        collected.append({
            "title": title,
            "description": description,
            "url": url,
            "host": host,
            "category": "web",
            "retrieval_score": _general_score(title, description, query, provider_rank),
            "source_tier": "web",
            "source_name": host,
            "source_country": None,
            "official_source": False,
            "query_index": 0,
        })


def search_general_web(
    query,
    *,
    requester=requests.get,
    poster=requests.post,
):
    """Run one neutral live-web query using NameMachine's existing providers."""
    cleaned = base_search._clean_text(query, 1800)
    if len(cleaned) < 2:
        raise ValueError("Query must contain at least 2 characters")

    providers = base_search._provider_config()
    provider = (
        "brave_web"
        if providers["brave"]
        else "browser_eye_web"
        if providers["browser_eye"]
        else "none"
    )
    general_intent = infer_general_intent(cleaned)

    if provider == "none":
        return {
            "query": cleaned,
            "category": "all",
            "country": None,
            "provider": "none",
            "provider_status": "unconfigured",
            "results": [],
            "search_plan": [cleaned],
            "intelligence_version": "general-web-v1",
            "intelligence_route": "general_web",
            "general_intent": general_intent,
            "truth_note": "No live web provider is configured; no search claims were generated.",
        }

    try:
        if provider == "brave_web":
            status, rows = base_search._brave_query(
                cleaned, providers["brave_key"], requester
            )
        else:
            status, rows = base_search._browser_eye_query(
                cleaned,
                providers["browser_url"],
                providers["browser_token"],
                poster,
            )
    except requests.RequestException:
        status, rows = "network_error", []
    except (TypeError, ValueError):
        status, rows = "malformed", []

    collected = []
    _decorate_general_rows(rows, cleaned, collected, set())
    collected.sort(
        key=lambda row: (
            -int(row.get("retrieval_score", 0)),
            str(row.get("title", "")).casefold(),
        )
    )

    return {
        "query": cleaned,
        "category": "all",
        "country": None,
        "provider": provider,
        "provider_status": status,
        "results": collected[:40],
        "search_plan": [cleaned],
        "intelligence_version": "general-web-v1",
        "intelligence_route": "general_web",
        "general_intent": general_intent,
        "truth_note": (
            "Web results are retrieval evidence. Titles and snippets are not "
            "independently verified facts; verify material claims at the original source."
        ),
    }


def search_universal(
    query,
    *,
    category="all",
    country="EU",
    requester=requests.get,
    poster=requests.post,
    opportunity_searcher=search_opportunity,
    general_searcher=search_general_web,
):
    """Route one private-mode query to the narrowest justified intelligence lane."""
    decision = classify_search_route(query, category=category)

    if decision["route"] == "opportunity":
        payload = opportunity_searcher(
            query,
            category=decision["routed_category"],
            country=country,
            requester=requester,
            poster=poster,
        )
        payload["intelligence_route"] = "opportunity"
        payload["route_reason"] = decision["reason"]
        payload["requested_category"] = decision["requested_category"]
        payload["routed_category"] = decision["routed_category"]
        payload["general_intent"] = None
        return payload

    payload = general_searcher(query, requester=requester, poster=poster)
    payload["intelligence_route"] = "general_web"
    payload["route_reason"] = decision["reason"]
    payload["requested_category"] = decision["requested_category"]
    payload["routed_category"] = decision["routed_category"]
    payload["general_intent"] = decision["general_intent"]
    payload["intent_routed"] = False
    return payload


def universal_search_capabilities() -> dict:
    payload = dict(base_search.global_search_capabilities())
    opportunity = opportunity_search_capabilities()
    payload.update({
        "intelligence_version": "universal-router-v1",
        "default_route": "auto",
        "routes": ["general_web", "opportunity"],
        "natural_language_intent_routing": True,
        "general_web": {
            "neutral_geography": True,
            "forced_opportunity_terms": False,
            "specialized_interpretation": False,
        },
        "opportunity": {
            "intelligence_version": opportunity.get("intelligence_version"),
            "priority_scope": opportunity.get("priority_scope", []),
            "priority_categories": opportunity.get("priority_categories", []),
            "deep_source_verification": bool(opportunity.get("deep_source_verification")),
        },
    })
    return payload


__all__ = [
    "classify_search_route",
    "infer_general_intent",
    "search_general_web",
    "search_universal",
    "universal_search_capabilities",
]
