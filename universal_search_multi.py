"""Multi-intent composition layer for NameMachine Universal Search.

This module keeps the proven single-route router intact and composes compatible
research lanes over the same provider transport. Exact user wording is queried
once, then at most one bounded expansion per selected module is allowed.
"""
from __future__ import annotations

import re

import requests

import global_search as base_search
import universal_search as single_search
from intelligence_modules import MODULE_BY_NAME, build_module_search_plan, source_affinity
from multi_intent_planner import MAX_MULTI_ROUTES, multi_intent_capabilities, plan_research_routes
from opportunity_search import search_global as search_opportunity


MULTI_EXACT_RESULT_TARGET = 12


def infer_general_intents(query: object) -> list[str]:
    """Return every coarse generic facet in deterministic confidence order."""
    text = " ".join(str(query or "").split()).casefold()
    scores = {}
    order = list(single_search.GENERAL_INTENT_PATTERNS)
    for intent, patterns in single_search.GENERAL_INTENT_PATTERNS.items():
        hits = sum(1 for pattern in patterns if re.search(pattern, text, flags=re.I))
        if hits:
            scores[intent] = hits
    if not scores:
        return ["general"]
    return sorted(scores, key=lambda name: (-scores[name], order.index(name)))


def classify_search_plan(query: object, *, category: object = "all") -> dict:
    """Return a backward-compatible primary route plus a bounded route set."""
    single = single_search.classify_search_route(query, category=category)
    if single["route"] == "opportunity":
        payload = dict(single)
        payload.update({
            "primary_route": "opportunity",
            "routes": ["opportunity"],
            "general_intents": [],
            "multi_intent": False,
            "module_versions": {},
            "module_candidates": [],
        })
        return payload

    facets = infer_general_intents(query)
    research = plan_research_routes(query)
    routes = list(research["routes"])
    if not routes:
        payload = dict(single)
        payload.update({
            "primary_route": "general_web",
            "routes": ["general_web"],
            "general_intents": facets,
            "multi_intent": False,
            "module_versions": {},
            "module_candidates": research["candidates"],
        })
        return payload

    if len(routes) == 1:
        payload = dict(single)
        payload.update({
            "primary_route": routes[0],
            "routes": routes,
            "general_intents": facets,
            "multi_intent": False,
            "module_versions": research["module_versions"],
            "module_candidates": research["candidates"],
        })
        return payload

    return {
        "route": "multi",
        "primary_route": research["primary_route"],
        "routes": routes,
        "reason": research["reason"],
        "requested_category": "all",
        "routed_category": "all",
        "general_intent": facets[0],
        "general_intents": facets,
        "module_confidence": research["module_confidence"],
        "module_version": research["module_version"],
        "module_versions": research["module_versions"],
        "module_candidates": research["candidates"],
        "multi_intent": True,
    }


def _clean_routes(routes: object) -> list[str]:
    cleaned = []
    for raw in routes if isinstance(routes, (list, tuple)) else []:
        route = str(raw or "").strip().lower()
        if route in MODULE_BY_NAME and route not in cleaned:
            cleaned.append(route)
        if len(cleaned) >= MAX_MULTI_ROUTES:
            break
    if len(cleaned) < 2:
        raise ValueError("Multi-intent search requires at least two valid routes")
    return cleaned


def _decorate_multi_rows(
    raw_rows,
    query,
    collected,
    row_by_canonical,
    *,
    routes,
    lane,
    query_index,
):
    for provider_rank, raw in enumerate(raw_rows if isinstance(raw_rows, list) else []):
        if not isinstance(raw, dict):
            continue
        title = base_search._clean_text(raw.get("title"), 300)
        description = base_search._clean_text(raw.get("description"), 900)
        url = base_search._clean_text(raw.get("url"), 1000)
        canonical = base_search._canonical_url(url)
        if not title or not canonical:
            continue
        host = base_search._host(url)
        affinity_by_route = {route: source_affinity(route, host) for route in routes}
        affinity = max(affinity_by_route.values(), default=0)
        score = single_search._general_score(title, description, query, provider_rank)
        if affinity:
            score = min(100, score + affinity)
        if query_index == 0:
            score = min(100, score + 3)

        existing = row_by_canonical.get(canonical)
        if existing is not None:
            existing["retrieval_score"] = max(int(existing["retrieval_score"]), score)
            existing["source_affinity"] = max(int(existing["source_affinity"]), affinity)
            existing["preferred_source_match"] = bool(existing["source_affinity"])
            for route, value in affinity_by_route.items():
                existing["source_affinity_routes"][route] = max(
                    int(existing["source_affinity_routes"].get(route, 0)),
                    int(value),
                )
            if lane not in existing["evidence_lanes"]:
                existing["evidence_lanes"].append(lane)
            if query_index not in existing["query_indexes"]:
                existing["query_indexes"].append(query_index)
                existing["query_indexes"].sort()
            continue

        row = {
            "title": title,
            "description": description,
            "url": url,
            "host": host,
            "category": routes[0],
            "retrieval_score": score,
            "source_tier": "web",
            "source_name": host,
            "source_country": None,
            "official_source": False,
            "source_affinity": affinity,
            "source_affinity_routes": affinity_by_route,
            "preferred_source_match": bool(affinity),
            "query_index": query_index,
            "query_indexes": [query_index],
            "query_lane": lane,
            "evidence_lanes": [lane],
            "intelligence_route": routes[0],
            "intelligence_routes": list(routes),
        }
        row_by_canonical[canonical] = row
        collected.append(row)


def search_multi_module_web(
    query,
    *,
    routes,
    requester=requests.get,
    poster=requests.post,
):
    """Search compatible modules with one shared exact query and bounded expansions."""
    cleaned = base_search._clean_text(query, 1800)
    if len(cleaned) < 2:
        raise ValueError("Query must contain at least 2 characters")
    routes = _clean_routes(routes)
    provider, providers = single_search._provider_choice()
    facets = infer_general_intents(cleaned)
    module_versions = {route: MODULE_BY_NAME[route].version for route in routes}

    if provider == "none":
        return {
            "query": cleaned,
            "category": "all",
            "country": None,
            "provider": "none",
            "provider_status": "unconfigured",
            "provider_status_by_lane": {},
            "results": [],
            "search_plan": [cleaned],
            "search_lanes": [{"lane": "shared", "query": cleaned, "routes": list(routes)}],
            "intelligence_version": "multi-intent-v1",
            "intelligence_route": routes[0],
            "intelligence_routes": list(routes),
            "module_versions": module_versions,
            "general_intent": facets[0],
            "general_intents": facets,
            "multi_intent": True,
            "truth_note": "No live web provider is configured; no search claims were generated.",
        }

    collected = []
    row_by_canonical = {}
    statuses = []
    status_by_lane = {}
    executed = []
    search_lanes = []

    def run_lane(search_query: str, *, lane: str, lane_routes: list[str], query_index: int):
        executed.append(search_query)
        search_lanes.append({"lane": lane, "query": search_query, "routes": list(lane_routes)})
        try:
            status, rows = single_search._run_provider_query(
                search_query,
                provider,
                providers,
                requester,
                poster,
            )
        except requests.RequestException:
            status, rows = "network_error", []
        except (TypeError, ValueError):
            status, rows = "malformed", []
        statuses.append(status)
        status_by_lane[lane] = status
        _decorate_multi_rows(
            rows,
            cleaned,
            collected,
            row_by_canonical,
            routes=routes,
            lane=lane,
            query_index=query_index,
        )
        return status

    exact_status = run_lane(
        cleaned,
        lane="shared",
        lane_routes=routes,
        query_index=0,
    )

    if exact_status != "complete" or len(collected) < MULTI_EXACT_RESULT_TARGET:
        seen_queries = {cleaned.casefold()}
        for route in routes:
            plan = build_module_search_plan(cleaned, route)
            expansion = next(
                (candidate for candidate in plan[1:] if candidate.casefold() not in seen_queries),
                None,
            )
            if not expansion:
                continue
            seen_queries.add(expansion.casefold())
            run_lane(
                expansion,
                lane=route,
                lane_routes=[route],
                query_index=len(executed),
            )

    collected.sort(
        key=lambda row: (
            -int(row.get("retrieval_score", 0)),
            min(row.get("query_indexes") or [99]),
            str(row.get("title", "")).casefold(),
        )
    )
    status = "complete" if collected and "complete" in statuses else (
        statuses[-1] if statuses else "unknown"
    )
    return {
        "query": cleaned,
        "category": "all",
        "country": None,
        "provider": provider,
        "provider_status": status,
        "provider_status_by_lane": status_by_lane,
        "results": collected[:40],
        "search_plan": executed,
        "search_lanes": search_lanes,
        "intelligence_version": "multi-intent-v1",
        "intelligence_route": routes[0],
        "intelligence_routes": list(routes),
        "module_versions": module_versions,
        "general_intent": facets[0],
        "general_intents": facets,
        "multi_intent": True,
        "truth_note": (
            "Multi-intent planning changes retrieval planning, evidence fusion and ranking only. "
            "Search snippets, marketplace listings and preferred-source matches remain retrieval "
            "evidence, not verified prices, availability, opening hours or other facts."
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
    general_searcher=single_search.search_general_web,
    module_searcher=single_search.search_module_web,
    multi_searcher=search_multi_module_web,
):
    """Execute one single- or multi-intent private Global Search request."""
    decision = classify_search_plan(query, category=category)

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
    elif decision["route"] == "multi":
        payload = multi_searcher(
            query,
            routes=decision["routes"],
            requester=requester,
            poster=poster,
        )
        payload["intelligence_route"] = decision["primary_route"]
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
    payload["general_intents"] = decision["general_intents"]
    payload["module_confidence"] = decision["module_confidence"]
    payload["module_version"] = decision["module_version"]
    payload["module_versions"] = decision["module_versions"]
    payload["module_candidates"] = decision["module_candidates"]
    payload["intelligence_routes"] = decision["routes"]
    payload["multi_intent"] = bool(decision["multi_intent"])
    payload["intent_routed"] = decision["route"] != "general_web"
    return payload


def universal_search_capabilities() -> dict:
    payload = dict(single_search.universal_search_capabilities())
    payload.update({
        "intelligence_version": "universal-router-v3",
        "routes": [
            route for route in payload.get("routes", []) if route != "multi"
        ] + ["multi"],
        "natural_language_multi_intent_planning": True,
        "multi_intent": multi_intent_capabilities(),
    })
    return payload


__all__ = [
    "classify_search_plan",
    "infer_general_intents",
    "search_multi_module_web",
    "search_universal",
    "universal_search_capabilities",
]
