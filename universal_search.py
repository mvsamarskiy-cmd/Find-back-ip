"""Universal intelligence router for NameMachine private Global Search.

Opportunity Intelligence remains a separate truth-aware vertical. Other research
modules influence routing, query planning, and retrieval ranking only; they do
not upgrade snippets or preferred hosts into verified facts.
"""
from __future__ import annotations

import re

import requests

import global_search as base_search
from intelligence_modules import (
    MODULE_BY_NAME,
    build_module_search_plan,
    classify_research_module,
    intelligence_module_capabilities,
    source_affinity,
)
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
    r"\bприз(?:и|ів|ом|ами|у|а)?\b", r"\bможливост\w*\b", r"\bзнайд\w*\b", r"\bвідкрит\w*\b",
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
    """Choose the narrowest high-confidence route while keeping fallback neutral."""
    requested = str(category or "all").strip().lower().replace("-", "_")
    if requested != "all":
        return {
            "route": "opportunity",
            "reason": "explicit_category",
            "requested_category": requested,
            "routed_category": requested,
            "general_intent": None,
            "module_confidence": 100,
            "module_version": None,
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
            "module_confidence": 100,
            "module_version": None,
        }

    module = classify_research_module(query)
    if module["route"] != "general_web":
        return {
            "route": module["route"],
            "reason": module["reason"],
            "requested_category": "all",
            "routed_category": "all",
            "general_intent": infer_general_intent(query),
            "module_confidence": module["confidence"],
            "module_version": module["module_version"],
        }

    return {
        "route": "general_web",
        "reason": "no_specialized_intent",
        "requested_category": "all",
        "routed_category": "all",
        "general_intent": infer_general_intent(query),
        "module_confidence": 0,
        "module_version": None,
    }


def _provider_choice() -> tuple[str, dict]:
    providers = base_search._provider_config()
    provider = (
        "brave_web"
        if providers["brave"]
        else "browser_eye_web"
        if providers["browser_eye"]
        else "none"
    )
    return provider, providers


def _run_provider_query(search_query, provider, providers, requester, poster):
    if provider == "brave_web":
        return base_search._brave_query(search_query, providers["brave_key"], requester)
    return base_search._browser_eye_query(
        search_query,
        providers["browser_url"],
        providers["browser_token"],
        poster,
    )


def _general_score(title: str, description: str, query: str, provider_rank: int) -> int:
    text = f"{title} {description}".casefold()
    tokens = base_search._query_tokens(query)
    token_hits = sum(1 for token in tokens if token in text)
    score = max(0, 55 - min(provider_rank, 35))
    score += min(35, token_hits * 7)
    return max(0, min(100, score))


def _decorate_rows(raw_rows, query, collected, seen, *, route="general_web", query_index=0):
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
        affinity = source_affinity(route, host) if route != "general_web" else 0
        score = _general_score(title, description, query, provider_rank)
        if affinity:
            score = min(100, score + affinity)
        if query_index == 0:
            score = min(100, score + 3)
        collected.append({
            "title": title,
            "description": description,
            "url": url,
            "host": host,
            "category": "web" if route == "general_web" else route,
            "retrieval_score": score,
            "source_tier": "web",
            "source_name": host,
            "source_country": None,
            "official_source": False,
            "source_affinity": affinity,
            "preferred_source_match": bool(affinity),
            "query_index": query_index,
            "intelligence_route": route,
        })


def _unconfigured_payload(query, *, route, search_plan, general_intent):
    return {
        "query": query,
        "category": "all",
        "country": None,
        "provider": "none",
        "provider_status": "unconfigured",
        "results": [],
        "search_plan": search_plan,
        "intelligence_version": (
            "general-web-v1" if route == "general_web" else MODULE_BY_NAME[route].version
        ),
        "intelligence_route": route,
        "general_intent": general_intent,
        "truth_note": "No live web provider is configured; no search claims were generated.",
    }


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

    provider, providers = _provider_choice()
    general_intent = infer_general_intent(cleaned)
    if provider == "none":
        return _unconfigured_payload(
            cleaned,
            route="general_web",
            search_plan=[cleaned],
            general_intent=general_intent,
        )

    try:
        status, rows = _run_provider_query(cleaned, provider, providers, requester, poster)
    except requests.RequestException:
        status, rows = "network_error", []
    except (TypeError, ValueError):
        status, rows = "malformed", []

    collected = []
    _decorate_rows(rows, cleaned, collected, set(), route="general_web", query_index=0)
    collected.sort(key=lambda row: (-int(row.get("retrieval_score", 0)), str(row.get("title", "")).casefold()))

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


def search_module_web(
    query,
    *,
    route,
    requester=requests.get,
    poster=requests.post,
):
    """Run one specialized retrieval module with bounded query expansion."""
    cleaned = base_search._clean_text(query, 1800)
    if len(cleaned) < 2:
        raise ValueError("Query must contain at least 2 characters")
    route = str(route or "").strip().lower()
    if route not in MODULE_BY_NAME:
        raise ValueError("Unknown intelligence module")

    planned = build_module_search_plan(cleaned, route)
    provider, providers = _provider_choice()
    general_intent = infer_general_intent(cleaned)
    if provider == "none":
        return _unconfigured_payload(
            cleaned,
            route=route,
            search_plan=planned,
            general_intent=general_intent,
        )

    collected, seen, statuses, executed = [], set(), [], []
    for query_index, search_query in enumerate(planned):
        executed.append(search_query)
        try:
            status, rows = _run_provider_query(search_query, provider, providers, requester, poster)
        except requests.RequestException:
            status, rows = "network_error", []
        except (TypeError, ValueError):
            status, rows = "malformed", []
        statuses.append(status)
        _decorate_rows(
            rows,
            cleaned,
            collected,
            seen,
            route=route,
            query_index=query_index,
        )
        # Keep the fast path fast. Expansion is only used when the exact query
        # does not already return a healthy result set.
        if status == "complete" and len(collected) >= 10:
            break

    collected.sort(key=lambda row: (-int(row.get("retrieval_score", 0)), int(row.get("query_index", 0)), str(row.get("title", "")).casefold()))
    status = "complete" if collected and "complete" in statuses else (statuses[-1] if statuses else "unknown")
    return {
        "query": cleaned,
        "category": "all",
        "country": None,
        "provider": provider,
        "provider_status": status,
        "results": collected[:40],
        "search_plan": executed,
        "intelligence_version": MODULE_BY_NAME[route].version,
        "intelligence_route": route,
        "general_intent": general_intent,
        "truth_note": (
            f"{route.title()} Intelligence changes retrieval planning and ranking only. "
            "Search snippets and preferred-source matches are evidence, not verified facts."
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
    module_searcher=search_module_web,
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
    elif decision["route"] == "general_web":
        payload = general_searcher(query, requester=requester, poster=poster)
        payload["intelligence_route"] = "general_web"
    else:
        payload = module_searcher(
            query,
            route=decision["route"],
            requester=requester,
            poster=poster,
        )
        payload["intelligence_route"] = decision["route"]

    payload["route_reason"] = decision["reason"]
    payload["requested_category"] = decision["requested_category"]
    payload["routed_category"] = decision["routed_category"]
    payload["general_intent"] = decision["general_intent"]
    payload["module_confidence"] = decision["module_confidence"]
    payload["module_version"] = decision["module_version"]
    payload["intent_routed"] = decision["route"] != "general_web"
    return payload


def universal_search_capabilities() -> dict:
    payload = dict(base_search.global_search_capabilities())
    opportunity = opportunity_search_capabilities()
    modules = intelligence_module_capabilities()
    payload.update({
        "intelligence_version": "universal-router-v2",
        "default_route": "auto",
        "routes": ["general_web", "opportunity", *modules.keys()],
        "natural_language_intent_routing": True,
        "general_web": {
            "neutral_geography": True,
            "forced_opportunity_terms": False,
            "specialized_interpretation": False,
        },
        "modules": modules,
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
    "search_module_web",
    "search_universal",
    "universal_search_capabilities",
]
