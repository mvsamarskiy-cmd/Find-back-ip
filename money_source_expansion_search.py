"""Bounded Source Expansion wrapper for Money / Material Opportunity Intelligence v2.4.

The base Money v2.2 search remains authoritative for exact/mechanism/Tor lanes.
This wrapper adds bounded source-class discovery, normalizes new evidence through
the same Money pipeline, merges cross-source candidates, reapplies eligibility,
and finally recompiles Opportunity Graph v2.3 across the complete result set.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import requests

import global_search as base_web
from money_eligibility_apply import apply_eligibility_to_payload
from money_intelligence import normalize_money_payload
from money_opportunity_graph import attach_graph_to_payload, opportunity_graph_capabilities
from money_opportunity_search import (
    _enabled_direct_verification,
    _project_records_to_results,
    _provider_choice,
    _run_standard,
    money_opportunity_search_capabilities as base_money_capabilities,
    search_money_opportunities as base_money_search,
)
from money_query_planner import compile_money_profile
from money_source_expansion import (
    MAX_SOURCE_EXPANSION_LANES,
    build_source_expansion_lanes,
    expanded_source_for_host,
    source_expansion_capabilities,
)
from money_taxonomy import TYPE_BY_ID, infer_money_types
from money_verification import apply_money_verification
from opportunity_intelligence import enrich_payload


SOURCE_EXPANSION_SEARCH_VERSION = "money-source-expansion-search-v2.4"
MAX_SOURCE_EXPANSION_CONCURRENCY = 3
MAX_EXPANDED_RAW_RESULTS = 80
MAX_EXPANDED_DIRECT_VERIFY = 2


def _safe_provider_call(lane: dict, *, provider: str, providers: dict, requester, poster):
    try:
        return _run_standard(
            lane["query"], provider=provider, providers=providers,
            requester=requester, poster=poster,
        )
    except requests.RequestException:
        return "network_error", []
    except (TypeError, ValueError):
        return "malformed", []
    except Exception:
        return "error", []


def _run_source_lanes(lanes: list[dict], *, provider: str, providers: dict, requester, poster):
    outcomes: dict[int, tuple[str, list]] = {}
    if not lanes:
        return []
    with ThreadPoolExecutor(max_workers=min(MAX_SOURCE_EXPANSION_CONCURRENCY, len(lanes))) as pool:
        futures = {
            pool.submit(
                _safe_provider_call, lane, provider=provider, providers=providers,
                requester=requester, poster=poster,
            ): index
            for index, lane in enumerate(lanes)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                outcomes[index] = future.result()
            except Exception:
                outcomes[index] = ("error", [])
    return [outcomes.get(index, ("unknown", [])) for index in range(len(lanes))]


def _expanded_affinity(source: dict | None, *, family: str | None, type_id: str | None) -> int:
    if not source:
        return 0
    score = {"official": 24, "public": 18, "platform": 10, "market": 7}.get(source.get("tier"), 4)
    if family and family in set(source.get("families") or []):
        score += 8
    if type_id and type_id in set(source.get("types") or []):
        score += 10
    return min(42, score)


def _decorate_expanded(raw_rows, *, original_query: str, profile: dict, lane: dict, lane_index: int, seen_urls: set[str]):
    output = []
    requested_types = profile.get("requested_types") or []
    for provider_rank, raw in enumerate(raw_rows if isinstance(raw_rows, list) else []):
        title = base_web._clean_text(raw.get("title"), 300)
        description = base_web._clean_text(raw.get("description"), 1200)
        url = base_web._clean_text(raw.get("url"), 1600)
        canonical = base_web._canonical_url(url)
        if not title or not canonical or canonical in seen_urls:
            continue
        seen_urls.add(canonical)
        host = base_web._host(url)
        expanded = expanded_source_for_host(host)
        observed_types = infer_money_types(f"{title} {description}", limit=5)
        type_id = observed_types[0] if observed_types else (requested_types[0] if requested_types else "other_monetizable_signal")
        family = TYPE_BY_ID.get(type_id, TYPE_BY_ID["other_monetizable_signal"]).family
        retrieval_score = base_web._score_result(
            title, description, None, original_query, 150 + lane_index * 20 + provider_rank,
        )
        retrieval_score = min(100, retrieval_score + _expanded_affinity(expanded, family=family, type_id=type_id))
        output.append({
            "title": title,
            "description": description,
            "url": url,
            "host": host,
            "category": type_id,
            "money_family_hint": family,
            "retrieval_score": retrieval_score,
            "source_tier": expanded.get("tier") if expanded else "web",
            "source_name": expanded.get("name") if expanded else host,
            "source_country": expanded.get("country") if expanded else None,
            "source_class": expanded.get("source_class") if expanded else lane.get("source_class"),
            "source_expansion_lane": lane.get("source_class"),
            "source_expansion_trust": lane.get("trust"),
            "source_registry_match": bool(expanded),
            "official_source": bool(expanded and expanded.get("tier") == "official"),
            "query_index": 100 + lane_index,
            "query_lane": "source_class_expansion",
            "query_family": None,
            "source_probe_domain": expanded.get("domain") if expanded else None,
            "transport": "web",
            "onion_service": False,
            "verification": {"verified": False, "state": "source_expansion_retrieval_evidence"},
        })
    return output


def _record_strength(record: dict) -> tuple:
    direct = record.get("direct_verification") if isinstance(record.get("direct_verification"), dict) else {}
    return (
        int(bool(record.get("current_call_verified"))),
        int(bool(direct.get("source_observed") or record.get("source_observed"))),
        int(record.get("evidence_score") or 0),
        int((record.get("practical_ranking") or {}).get("score") or 0),
    )


def _merge_record_pair(left: dict, right: dict) -> dict:
    primary, secondary = (left, right) if _record_strength(left) >= _record_strength(right) else (right, left)
    merged = deepcopy(primary)
    merged["source_urls"] = list(dict.fromkeys([*(left.get("source_urls") or []), *(right.get("source_urls") or [])]))[:30]
    merged["duplicate_evidence_count"] = int(left.get("duplicate_evidence_count") or 1) + int(right.get("duplicate_evidence_count") or 1)
    merged["official_source"] = bool(left.get("official_source") or right.get("official_source"))
    merged["source_observed"] = bool(left.get("source_observed") or right.get("source_observed"))
    merged["current_call_verified"] = bool(left.get("current_call_verified") or right.get("current_call_verified"))
    merged["evidence_score"] = max(int(left.get("evidence_score") or 0), int(right.get("evidence_score") or 0))
    merged["source_expansion_evidence"] = True
    expanded_classes = []
    for record in (left, right):
        value = record.get("source_class") or (record.get("retrieval") or {}).get("source_class")
        if value and value not in expanded_classes:
            expanded_classes.append(value)
    if expanded_classes:
        merged["source_classes"] = expanded_classes
    return merged


def _merge_records(base_records: list[dict], expanded_records: list[dict]) -> tuple[list[dict], int]:
    merged: dict[str, dict] = {}
    base_keys = set()
    for record in base_records:
        if not isinstance(record, dict):
            continue
        key = str(record.get("dedupe_fingerprint") or record.get("opportunity_id") or "")
        if not key:
            continue
        merged[key] = deepcopy(record)
        base_keys.add(key)
    added = 0
    for record in expanded_records:
        if not isinstance(record, dict):
            continue
        key = str(record.get("dedupe_fingerprint") or record.get("opportunity_id") or "")
        if not key:
            continue
        if key in merged:
            merged[key] = _merge_record_pair(merged[key], record)
        else:
            row = deepcopy(record)
            row["source_expansion_evidence"] = True
            merged[key] = row
            added += 1
    return list(merged.values()), added


def _recompute_money_summary(records: list[dict]) -> dict:
    summary = {}
    for record in records:
        family = str(record.get("family") or "other")
        bucket = summary.setdefault(family, {
            "found": 0, "open": 0, "upcoming": 0, "likely_eligible": 0, "official_source": 0,
        })
        bucket["found"] += 1
        if record.get("status") in {"open", "upcoming"}:
            bucket[record["status"]] += 1
        if record.get("likely_eligible"):
            bucket["likely_eligible"] += 1
        if record.get("official_source"):
            bucket["official_source"] += 1
    return summary


def _expanded_result_rows(expanded_payload: dict) -> list[dict]:
    records_by_url = {}
    for record in expanded_payload.get("money_records") or []:
        for url in record.get("source_urls") or []:
            records_by_url[url] = record
    rows = []
    for raw in expanded_payload.get("results") or []:
        row = dict(raw)
        record = records_by_url.get(str(row.get("url") or ""))
        if record:
            row["money_record"] = record
        rows.append(row)
    return rows


def search_money_opportunities(
    query, *, category="all", country="EU", requester=requests.get, poster=requests.post,
    evidence_fetcher=None,
):
    base = base_money_search(
        query, category=category, country=country, requester=requester, poster=poster,
        evidence_fetcher=evidence_fetcher,
    )
    profile = ((base.get("money_query_plan") or {}).get("profile") or base.get("money_profile") or compile_money_profile(query, country=country))
    lanes = build_source_expansion_lanes(profile)
    provider, providers = _provider_choice()

    if provider == "none" or not lanes:
        result = attach_graph_to_payload(base)
        result["source_expansion"] = {
            "version": SOURCE_EXPANSION_SEARCH_VERSION,
            "enabled": bool(lanes),
            "attempted": False,
            "lanes": lanes,
            "provider_statuses": [],
            "raw_candidate_count": 0,
            "unique_added_count": 0,
            "capabilities": source_expansion_capabilities(),
            "truth_semantics": "no_source_expansion_provider_calls_no_fabricated_candidates",
        }
        result["intelligence_version"] = SOURCE_EXPANSION_SEARCH_VERSION
        return result

    outcomes = _run_source_lanes(
        lanes, provider=provider, providers=providers, requester=requester, poster=poster,
    )
    seen_urls = {
        base_web._canonical_url(url)
        for record in (base.get("money_records") or [])
        for url in (record.get("source_urls") or [])
        if base_web._canonical_url(url)
    }
    expanded_raw = []
    statuses = []
    for lane_index, (lane, outcome) in enumerate(zip(lanes, outcomes)):
        status, raw_rows = outcome
        statuses.append(status)
        expanded_raw.extend(_decorate_expanded(
            raw_rows, original_query=profile.get("query") or str(query), profile=profile,
            lane=lane, lane_index=lane_index, seen_urls=seen_urls,
        ))
        if len(expanded_raw) >= MAX_EXPANDED_RAW_RESULTS:
            expanded_raw = expanded_raw[:MAX_EXPANDED_RAW_RESULTS]
            break

    expansion_payload = {
        "query": profile.get("query") or str(query),
        "category": category,
        "country": profile.get("country") or country,
        "provider": provider,
        "provider_status": "complete" if expanded_raw and "complete" in statuses else (statuses[-1] if statuses else "unknown"),
        "results": expanded_raw,
        "search_plan": [lane["query"] for lane in lanes],
        "search_lanes": lanes,
        "intelligence_version": SOURCE_EXPANSION_SEARCH_VERSION,
    }

    direct_enabled = _enabled_direct_verification() and bool(providers.get("browser_eye")) and bool(expanded_raw)
    enriched = enrich_payload(
        expansion_payload,
        query=profile.get("query") or str(query),
        country=profile.get("country") or country,
        requester=requester,
        verify_limit=0 if direct_enabled else 2,
    )
    expanded_rows = enriched.get("results") or []
    if direct_enabled:
        if evidence_fetcher is None:
            expanded_rows = apply_money_verification(expanded_rows, limit=MAX_EXPANDED_DIRECT_VERIFY)
        else:
            expanded_rows = apply_money_verification(
                expanded_rows, evidence_fetcher=evidence_fetcher, limit=MAX_EXPANDED_DIRECT_VERIFY,
            )
        enriched["results"] = expanded_rows

    expanded_normalized = normalize_money_payload(enriched, profile=profile)
    expanded_normalized = apply_eligibility_to_payload(
        expanded_normalized,
        eligibility_profile=profile.get("eligibility_profile") or {"facts": {}, "known_fields": []},
    )

    # Preserve source-class metadata on normalized records through URL mapping.
    class_by_url = {str(row.get("url") or ""): row.get("source_class") for row in expanded_rows if row.get("url")}
    for record in expanded_normalized.get("money_records") or []:
        classes = []
        for url in record.get("source_urls") or []:
            value = class_by_url.get(url)
            if value and value not in classes:
                classes.append(value)
        if classes:
            record["source_classes"] = classes
            record["source_class"] = classes[0]
            record.setdefault("retrieval", {})["source_class"] = classes[0]

    merged_records, unique_added = _merge_records(
        base.get("money_records") or [], expanded_normalized.get("money_records") or [],
    )
    merged_records = apply_eligibility_to_payload(
        {"money_records": merged_records},
        eligibility_profile=profile.get("eligibility_profile") or {"facts": {}, "known_fields": []},
    )["money_records"]

    result = dict(base)
    result["money_records"] = merged_records
    result["money_summary"] = _recompute_money_summary(merged_records)
    result["results"] = [*(base.get("results") or []), *_expanded_result_rows(expanded_normalized)]
    result = _project_records_to_results(result)
    result = attach_graph_to_payload(result)
    result["source_expansion"] = {
        "version": SOURCE_EXPANSION_SEARCH_VERSION,
        "enabled": True,
        "attempted": True,
        "lanes": lanes,
        "provider_statuses": statuses,
        "raw_candidate_count": len(expanded_raw),
        "normalized_candidate_count": len(expanded_normalized.get("money_records") or []),
        "unique_added_count": unique_added,
        "direct_verification_attempted_count": sum(1 for row in expanded_rows if row.get("money_direct_verification")),
        "capabilities": source_expansion_capabilities(),
        "truth_semantics": "expanded_source_discovery_candidates_not_current_or_eligible_or_profitable_by_source_membership",
    }
    result["intelligence_version"] = SOURCE_EXPANSION_SEARCH_VERSION
    return result


def money_opportunity_search_capabilities() -> dict:
    payload = dict(base_money_capabilities())
    payload["version"] = SOURCE_EXPANSION_SEARCH_VERSION
    payload["source_expansion"] = source_expansion_capabilities()
    payload["opportunity_graph"] = opportunity_graph_capabilities()
    payload["source_expansion_concurrency_max"] = MAX_SOURCE_EXPANSION_CONCURRENCY
    payload["expanded_direct_verify_max"] = MAX_EXPANDED_DIRECT_VERIFY
    payload["truth_semantics"] = "base_money_search_plus_bounded_source_class_discovery_plus_evidence_graph"
    return payload


__all__ = [
    "MAX_EXPANDED_DIRECT_VERIFY", "MAX_SOURCE_EXPANSION_CONCURRENCY", "SOURCE_EXPANSION_SEARCH_VERSION",
    "money_opportunity_search_capabilities", "search_money_opportunities",
]
