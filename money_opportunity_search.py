"""Broad Money / Material Opportunity Intelligence v2 search orchestrator.

The exact user wording is always retrieval lane zero.  Bounded deterministic
expansions then search mechanisms the user may not know by name.  A single Tor
exact-query lane is additive when Browser Eye is configured.  All outputs remain
retrieval/evidence candidates until source rules and economics are verified.
"""
from __future__ import annotations

import os
import requests
from urllib.parse import urlsplit

import global_search as base_search
from money_intelligence import money_intelligence_capabilities, normalize_money_payload
from money_query_planner import build_money_search_plan, money_query_planner_capabilities
from money_sources import source_affinity, source_catalog_capabilities, source_for_host
from money_taxonomy import infer_money_types, taxonomy_capabilities
from opportunity_intelligence import enrich_payload


MONEY_OPPORTUNITY_SEARCH_VERSION = "money-opportunity-search-v2"
MAX_RAW_RESULTS = 140


def _enabled_tor() -> bool:
    return str(os.environ.get("TOR_OPPORTUNITY_SEARCH_ENABLED", "1")).strip().casefold() not in {"0", "false", "no", "off"}


def _is_onion(url: object) -> bool:
    try:
        return (urlsplit(str(url or "")).hostname or "").lower().endswith(".onion")
    except ValueError:
        return False


def _provider_choice():
    providers = base_search._provider_config()
    provider = "brave_web" if providers["brave"] else "browser_eye_web" if providers["browser_eye"] else "none"
    return provider, providers


def _run_standard(search_query, *, provider, providers, requester, poster):
    if provider == "brave_web":
        return base_search._brave_query(search_query, providers["brave_key"], requester)
    return base_search._browser_eye_query(search_query, providers["browser_url"], providers["browser_token"], poster)


def _run_tor_exact(query, providers, poster):
    if not _enabled_tor() or not providers.get("browser_eye"):
        return "unconfigured", []
    response = poster(
        providers["browser_url"] + "/v1/tor-web-search",
        json={"query": query, "limit": 20},
        timeout=32,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "NameMachine-money-opportunity/2",
            "X-Global-Search-Token": providers["browser_token"],
        },
    )
    if response.status_code == 429:
        return "rate_limited", []
    if response.status_code != 200:
        return f"provider_http_{response.status_code}", []
    payload = response.json() if response.content else {}
    return str(payload.get("provider_status") or "complete"), [row for row in (payload.get("results") or [])[:20] if isinstance(row, dict)]


def _decorate(raw_rows, *, query, profile, lane, query_index, collected, seen, transport="web"):
    requested_types = profile.get("requested_types") or []
    requested_families = profile.get("requested_families") or []
    for provider_rank, raw in enumerate(raw_rows if isinstance(raw_rows, list) else []):
        title = base_search._clean_text(raw.get("title"), 300)
        description = base_search._clean_text(raw.get("description"), 1200)
        url = base_search._clean_text(raw.get("url"), 1600)
        canonical = base_search._canonical_url(url)
        if not title or not canonical:
            continue
        # One URL can be rediscovered by several mechanisms. Keep the strongest
        # first row here; cross-source duplicate titles are handled later by
        # Money Intelligence's entity-like fingerprint.
        if canonical in seen:
            continue
        seen.add(canonical)
        host = base_search._host(url)
        source = source_for_host(host)
        observed_types = infer_money_types(f"{title} {description}", limit=4)
        type_id = observed_types[0] if observed_types else (requested_types[0] if requested_types else "other_monetizable_signal")
        family = None
        try:
            from money_taxonomy import TYPE_BY_ID
            family = TYPE_BY_ID[type_id].family
        except Exception:
            family = lane.get("family") or "other"
        score = base_search._score_result(title, description, None, query, query_index * 20 + provider_rank)
        score = min(100, score + source_affinity(host, families=[family, *requested_families], types=[type_id, *requested_types]))
        if query_index == 0:
            score = min(100, score + 5)
        collected.append({
            "title": title,
            "description": description,
            "url": url,
            "host": host,
            "category": type_id,
            "money_family_hint": family,
            "retrieval_score": score,
            "source_tier": source["tier"] if source else ("tor" if transport == "tor" else "web"),
            "source_name": source["name"] if source else host,
            "source_country": source["country"] if source else None,
            "official_source": bool(source and source["tier"] == "official"),
            "query_index": query_index,
            "query_lane": lane.get("lane"),
            "query_family": lane.get("family"),
            "source_probe_domain": lane.get("source_domain"),
            "transport": transport,
            "onion_service": bool(raw.get("onion_service")) or _is_onion(url),
            "verification": {"verified": False, "state": f"{transport}_retrieval_evidence"},
        })


def _aggregate_status(statuses: list[str], result_count: int) -> str:
    if result_count and "complete" in statuses:
        return "complete"
    if not statuses:
        return "unknown"
    if all(status == "rate_limited" for status in statuses):
        return "rate_limited"
    return statuses[-1]


def search_money_opportunities(query, *, category="all", country="EU", requester=requests.get, poster=requests.post):
    plan = build_money_search_plan(query, country=country)
    profile = plan["profile"]
    provider, providers = _provider_choice()
    if provider == "none":
        return normalize_money_payload({
            "query": profile["query"],
            "category": category,
            "country": profile["country"],
            "provider": "none",
            "provider_status": "unconfigured",
            "results": [],
            "search_plan": plan["queries"],
            "search_lanes": plan["lanes"],
            "intelligence_version": MONEY_OPPORTUNITY_SEARCH_VERSION,
            "truth_note": "No live provider is configured; no opportunity candidates were generated.",
        }, profile=profile)

    collected, seen, statuses = [], set(), []
    executed_lanes = []
    for query_index, lane in enumerate(plan["lanes"]):
        search_query = lane["query"]
        executed_lanes.append(dict(lane))
        try:
            status, rows = _run_standard(
                search_query, provider=provider, providers=providers,
                requester=requester, poster=poster,
            )
        except requests.RequestException:
            status, rows = "network_error", []
        except (TypeError, ValueError):
            status, rows = "malformed", []
        statuses.append(status)
        _decorate(
            rows, query=profile["query"], profile=profile, lane=lane,
            query_index=query_index, collected=collected, seen=seen, transport="web",
        )

    tor_status, tor_rows = "not_attempted", []
    if _enabled_tor() and providers.get("browser_eye"):
        try:
            tor_status, tor_rows = _run_tor_exact(profile["query"], providers, poster)
        except requests.RequestException:
            tor_status, tor_rows = "network_error", []
        except (TypeError, ValueError):
            tor_status, tor_rows = "malformed", []
        tor_lane = {"query": profile["query"], "lane": "tor_exact", "family": None, "source_domain": None}
        _decorate(
            tor_rows, query=profile["query"], profile=profile, lane=tor_lane,
            query_index=0, collected=collected, seen=seen, transport="tor",
        )

    collected.sort(key=lambda row: (-int(row.get("official_source") or False), -int(row.get("retrieval_score") or 0), int(row.get("query_index") or 0)))
    raw_payload = {
        "query": profile["query"],
        "category": category,
        "country": profile["country"],
        "provider": provider,
        "provider_status": _aggregate_status(statuses, len(collected)),
        "results": collected[:MAX_RAW_RESULTS],
        "search_plan": [lane["query"] for lane in executed_lanes],
        "search_lanes": executed_lanes,
        "money_query_plan": plan,
        "tor_retrieval": {
            "attempted": bool(_enabled_tor() and providers.get("browser_eye")),
            "provider_status": tor_status,
            "exact_query_once": True,
            "transport": "tor",
            "truth_semantics": "tor_retrieval_evidence_not_verified_fact",
        },
        "intelligence_version": MONEY_OPPORTUNITY_SEARCH_VERSION,
    }

    # Reuse the stable v1 extractors/source verifier where applicable, then
    # compile the broader v2 record/ranking layer over every result.
    enriched = enrich_payload(raw_payload, query=profile["query"], country=profile["country"], requester=requester, verify_limit=6)
    result = normalize_money_payload(enriched, profile=profile)
    result["intelligence_version"] = MONEY_OPPORTUNITY_SEARCH_VERSION
    result["requested_category"] = str(category or "all")
    result["material_opportunity_intent"] = bool(profile.get("money_intent"))
    return result


def money_opportunity_search_capabilities() -> dict:
    return {
        "version": MONEY_OPPORTUNITY_SEARCH_VERSION,
        "taxonomy": taxonomy_capabilities(),
        "planner": money_query_planner_capabilities(),
        "sources": source_catalog_capabilities(),
        "intelligence": money_intelligence_capabilities(),
        "standard_exact_query_first": True,
        "tor_exact_query_max_calls": 1,
        "poland_eu_priority": True,
        "off_market_scope": "publicly_discoverable_only",
        "automated_purchase_or_contact": False,
        "truth_semantics": "discovery_not_current_status_not_eligibility_not_profit_guarantee",
    }


__all__ = [
    "MONEY_OPPORTUNITY_SEARCH_VERSION", "money_opportunity_search_capabilities",
    "search_money_opportunities",
]
