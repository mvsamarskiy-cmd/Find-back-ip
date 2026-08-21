"""Entity-resolution layer over Universal Search v4 synthesis.

The proven search planner/provider path and evidence synthesis remain unchanged.
This layer resolves product evidence into product families and exact variants,
then builds only entity-safe comparisons from already-retrieved observations.
"""
from __future__ import annotations

import requests

import universal_search_synthesis as synthesis_search
from entity_resolution import entity_resolution_capabilities, resolve_product_entities


def _entity_source_map(resolution: dict) -> dict[str, str]:
    mapping = {}
    for entity in resolution.get("entities", []):
        entity_id = entity.get("entity_id")
        if not entity_id:
            continue
        for url in entity.get("source_urls", []):
            mapping[url] = entity_id
    return mapping


def _safe_entities(resolution: dict) -> dict[str, dict]:
    return {
        entity["entity_id"]: entity
        for entity in resolution.get("entities", [])
        if entity.get("entity_id") and entity.get("comparison_safe")
    }


def _attach_entity_ids(synthesis: dict, resolution: dict) -> None:
    source_map = _entity_source_map(resolution)
    for source in synthesis.get("top_evidence", []):
        entity_id = source_map.get(source.get("url"))
        if entity_id:
            source["entity_id"] = entity_id
    for observation in synthesis.get("observations", []):
        entity_id = source_map.get(observation.get("source_url"))
        if entity_id:
            observation["entity_id"] = entity_id


def _price_comparisons(synthesis: dict, resolution: dict) -> list[dict]:
    safe = _safe_entities(resolution)
    grouped: dict[tuple[str, str], list[dict]] = {}
    for observation in synthesis.get("observations", []):
        if observation.get("type") != "price_mention":
            continue
        entity_id = observation.get("entity_id")
        currency = observation.get("currency")
        if entity_id not in safe or not currency:
            continue
        grouped.setdefault((entity_id, currency), []).append(observation)

    comparisons = []
    for (entity_id, currency), rows in sorted(grouped.items()):
        hosts = {row.get("source_host") for row in rows if row.get("source_host")}
        values = [float(row["value"]) for row in rows if row.get("value") is not None]
        if len(hosts) < 2 or len(values) < 2:
            continue
        entity = safe[entity_id]
        offers = []
        seen = set()
        for row in rows:
            signature = (row.get("source_url"), row.get("value"))
            if signature in seen:
                continue
            seen.add(signature)
            offers.append({
                "value": row.get("value"),
                "currency": currency,
                "source_url": row.get("source_url"),
                "source_host": row.get("source_host"),
                "retrieved_at": row.get("retrieved_at"),
                "independently_verified": bool(row.get("independently_verified")),
            })
        comparisons.append({
            "entity_id": entity_id,
            "family_id": entity.get("family_id"),
            "canonical_label": entity.get("canonical_label"),
            "variant": entity.get("variant"),
            "currency": currency,
            "min_observed": min(values),
            "max_observed": max(values),
            "spread": round(max(values) - min(values), 2),
            "offer_count": len(offers),
            "source_host_count": len(hosts),
            "offers": offers[:20],
            "status": "entity_resolved_retrieval_comparison",
            "verified_price_comparison": False,
        })
    return comparisons


def _entity_conflicts(synthesis: dict, resolution: dict) -> list[dict]:
    safe = _safe_entities(resolution)
    grouped: dict[tuple[str, str], list[dict]] = {}
    for observation in synthesis.get("observations", []):
        obs_type = observation.get("type")
        if obs_type not in {"availability_mention", "opening_status_mention"}:
            continue
        entity_id = observation.get("entity_id")
        if entity_id not in safe:
            continue
        grouped.setdefault((entity_id, obs_type), []).append(observation)

    conflicts = []
    for (entity_id, obs_type), rows in sorted(grouped.items()):
        values = sorted({str(row.get("value")) for row in rows if row.get("value")})
        hosts = sorted({row.get("source_host") for row in rows if row.get("source_host")})
        if len(values) < 2 or len(hosts) < 2:
            continue
        entity = safe[entity_id]
        conflicts.append({
            "entity_id": entity_id,
            "family_id": entity.get("family_id"),
            "canonical_label": entity.get("canonical_label"),
            "variant": entity.get("variant"),
            "kind": "availability_conflict" if obs_type == "availability_mention" else "opening_status_conflict",
            "status": "entity_resolved_conflict_needs_direct_verification",
            "observed_values": values,
            "source_hosts": hosts,
            "verified_conflict": False,
        })
    return conflicts


def apply_entity_resolution(payload: dict) -> dict:
    """Attach conservative product entity resolution to an existing v4 payload."""
    synthesis = payload.get("synthesis") if isinstance(payload.get("synthesis"), dict) else None
    routes = payload.get("intelligence_routes") if isinstance(payload.get("intelligence_routes"), list) else []
    if synthesis is None:
        return payload
    if "product" not in routes and payload.get("intelligence_route") != "product":
        synthesis["entity_resolution"] = {
            "version": "entity-resolution-v1",
            "mode": "not_applicable",
            "reason": "product_route_not_active",
        }
        synthesis["entity_price_comparisons"] = []
        synthesis["entity_conflict_candidates"] = []
        return payload

    resolution = resolve_product_entities(synthesis.get("top_evidence", []))
    _attach_entity_ids(synthesis, resolution)
    synthesis["entity_resolution"] = resolution
    synthesis["entity_price_comparisons"] = _price_comparisons(synthesis, resolution)
    synthesis["entity_conflict_candidates"] = _entity_conflicts(synthesis, resolution)
    truth_status = synthesis.setdefault("truth_status", {})
    truth_status["entity_resolution_available"] = True
    truth_status["entity_resolved_price_comparison_is_verified"] = False
    return payload


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
    }
    if opportunity_searcher is not None:
        kwargs["opportunity_searcher"] = opportunity_searcher
    if general_searcher is not None:
        kwargs["general_searcher"] = general_searcher
    if module_searcher is not None:
        kwargs["module_searcher"] = module_searcher
    if multi_searcher is not None:
        kwargs["multi_searcher"] = multi_searcher
    if synthesizer is not None:
        kwargs["synthesizer"] = synthesizer
    payload = synthesis_search.search_universal(query, **kwargs)
    return apply_entity_resolution(payload)


def universal_search_capabilities() -> dict:
    payload = dict(synthesis_search.universal_search_capabilities())
    payload.update({
        "intelligence_version": "universal-router-v5",
        "entity_resolution": entity_resolution_capabilities(),
    })
    return payload


__all__ = [
    "apply_entity_resolution",
    "search_universal",
    "universal_search_capabilities",
]
