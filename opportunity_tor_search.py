"""Opportunity search wrapper with one bounded Tor retrieval lane.

The standard opportunity search remains primary. When Browser Eye is configured,
this wrapper issues the exact user query once through the Tor transport and merges
new retrieval evidence before Opportunity Intelligence normalization. Tor evidence
is never treated as verified solely because it arrived over Tor or from .onion.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

import requests

import global_search as base_search
from opportunity_intelligence import enrich_payload
from opportunity_search import infer_query_category, opportunity_search_capabilities as base_capabilities


TOR_OPPORTUNITY_VERSION = "tor-opportunity-retrieval-v1"


def _enabled():
    return str(os.environ.get("TOR_OPPORTUNITY_SEARCH_ENABLED", "1")).strip().casefold() not in {"0", "false", "no", "off"}


def _is_onion(url: object) -> bool:
    try:
        host = (urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return False
    return host.endswith(".onion")


def _tor_query(query, providers, poster):
    if not _enabled() or not providers.get("browser_eye"):
        return "unconfigured", []
    response = poster(
        providers["browser_url"] + "/v1/tor-web-search",
        json={"query": query, "limit": 20},
        timeout=32,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "NameMachine-opportunity-tor/1",
            "X-Global-Search-Token": providers["browser_token"],
        },
    )
    if response.status_code == 429:
        return "rate_limited", []
    if response.status_code != 200:
        return f"provider_http_{response.status_code}", []
    payload = response.json() if response.content else {}
    rows = []
    for raw in (payload.get("results") or [])[:20]:
        if not isinstance(raw, dict):
            continue
        rows.append({
            "title": raw.get("title"),
            "description": raw.get("description"),
            "url": raw.get("url"),
            "transport": "tor",
            "onion_service": bool(raw.get("onion_service")) or _is_onion(raw.get("url")),
        })
    return str(payload.get("provider_status") or "complete"), rows


def _decorate_tor_rows(raw_rows, *, query, routed_category, country, existing):
    seen = {base_search._canonical_url(row.get("url")) for row in existing if isinstance(row, dict)}
    output = []
    for rank, raw in enumerate(raw_rows if isinstance(raw_rows, list) else []):
        title = base_search._clean_text(raw.get("title"), 300)
        description = base_search._clean_text(raw.get("description"), 900)
        url = base_search._clean_text(raw.get("url"), 1000)
        canonical = base_search._canonical_url(url)
        if not title or not canonical or canonical in seen:
            continue
        seen.add(canonical)
        host = base_search._host(url)
        source = base_search._source_for_host(host)
        category = base_search.infer_category(title, description, routed_category)
        score = base_search._score_result(title, description, source, query, 30 + rank)
        output.append({
            "title": title,
            "description": description,
            "url": url,
            "host": host,
            "category": category,
            "retrieval_score": score,
            "source_tier": source["tier"] if source else "tor",
            "source_name": source["name"] if source else host,
            "source_country": source["country"] if source else None,
            "official_source": bool(source and source["tier"] == "official"),
            "query_index": 0,
            "transport": "tor",
            "onion_service": bool(raw.get("onion_service")) or _is_onion(url),
            "verification": {"verified": False, "state": "tor_retrieval_evidence"},
        })
    return output


def search_global(query, *, category="all", country="EU", requester=requests.get, poster=requests.post):
    requested_category = str(category or "all").strip().lower()
    routed_category = infer_query_category(query) if requested_category == "all" else requested_category
    base_payload = base_search.search_global(
        query,
        category=routed_category,
        country=country,
        requester=requester,
        poster=poster,
    )
    rows = [dict(row) for row in (base_payload.get("results") or []) if isinstance(row, dict)]
    providers = base_search._provider_config()
    tor_status = "not_attempted"
    tor_raw = []
    if _enabled() and providers.get("browser_eye"):
        try:
            tor_status, tor_raw = _tor_query(base_search._clean_text(query, 1800), providers, poster)
        except requests.RequestException:
            tor_status, tor_raw = "network_error", []
        except (TypeError, ValueError):
            tor_status, tor_raw = "malformed", []
    tor_rows = _decorate_tor_rows(
        tor_raw,
        query=base_search._clean_text(query, 1200),
        routed_category=routed_category,
        country=country,
        existing=rows,
    )
    rows.extend(tor_rows)
    rows.sort(key=lambda row: (-int(row.get("official_source", False)), -int(row.get("retrieval_score", 0)), str(row.get("title", "")).casefold()))
    base_payload["results"] = rows[:80]
    base_payload["tor_retrieval"] = {
        "version": TOR_OPPORTUNITY_VERSION,
        "attempted": bool(_enabled() and providers.get("browser_eye")),
        "provider_status": tor_status,
        "result_count": len(tor_rows),
        "exact_query_once": True,
        "transport": "tor",
        "truth_semantics": "tor_retrieval_evidence_not_verified_fact",
    }
    enriched = enrich_payload(base_payload, query=query, country=country, requester=requester)
    enriched["requested_category"] = requested_category
    enriched["routed_category"] = routed_category
    enriched["intent_routed"] = requested_category == "all" and routed_category != "all"
    enriched["opportunity_transport_version"] = TOR_OPPORTUNITY_VERSION
    return enriched


def opportunity_search_capabilities():
    payload = dict(base_capabilities())
    payload["tor_retrieval"] = {
        "version": TOR_OPPORTUNITY_VERSION,
        "enabled_by_default": True,
        "exact_query_max_calls": 1,
        "onion_service_evidence": True,
        "onion_location_discovery": True,
        "verification_inferred_from_tor": False,
    }
    return payload


__all__ = ["TOR_OPPORTUNITY_VERSION", "opportunity_search_capabilities", "search_global"]
