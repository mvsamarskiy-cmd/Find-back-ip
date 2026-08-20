"""Authoritative claimability stage for NameMachine.

Fast public sensors and Browser Intelligence answer a different question from
claimability: they can prove that an identity exists or that no public identity was
observed, but they cannot manufacture a registration guarantee. This module is
the final, sparse stage that may promote a resource to strict green (`claimable`)
only when an authoritative provider explicitly confirms assignment/registration.

In production `STRICT_CLAIMABILITY_DEFERRED=1` moves expensive registrar and
Telegram assignment checks out of the foreground critical path and lets the
durable Browser Intelligence queue run them after cheap evidence has screened a
candidate.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import os
from typing import Any
from urllib.parse import quote

import requests

import availability
import telegram_integration
from final_ranking import annotate_candidate, strict_availability_state
from identity_bundle import classify_identity_bundle
from telegram_evidence import fetch_telegram_evidence


STRICT_RESOURCES = ("com", "telegram")
DECISIVE_STRICT_STATUSES = frozenset({"claimable", "purchasable", "taken", "reserved", "invalid"})
PROBEABLE_STATUSES = frozenset({"not_found", "unknown", "rate_limited"})
HARD_CONFLICT = frozenset({"taken", "reserved", "invalid"})
STRICT_SERVER_KEYS = (
    "strict_claimability",
    "strict_claimability_state",
    "strict_claimability_unprovable_required",
    "bundle_state",
    "bundle_score",
    "bundle_availability_state",
    "bundle_claimable",
    "bundle_purchasable",
    "structural_quality_score",
    "linguistic_quality_score",
    "name_quality_score",
    "user_fit_score",
    "adaptive_relevance_score",
    "identity_relevance_score",
    "availability_opportunity_score",
    "availability_evidence_confidence_score",
    "verification_coverage_score",
    "final_score",
    "availability_state",
    "ranking_model",
    "ranking_reason",
)


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def deferred_enabled() -> bool:
    return _truthy(os.environ.get("STRICT_CLAIMABILITY_DEFERRED", "0"))


def _configured(*names: str) -> bool:
    return all(bool(str(os.environ.get(name) or "").strip()) for name in names)


def strict_claimability_capabilities() -> dict[str, Any]:
    namecom = _configured("NAMECOM_USERNAME", "NAMECOM_API_TOKEN")
    telegram = _configured("TELEGRAM_EVIDENCE_URL", "TELEGRAM_EVIDENCE_TOKEN")
    resources = {
        "com": {
            "provider": "name.com",
            "method": "registrar_check_availability",
            "configured": namecom,
            "authoritative_claimability": True,
            "can_turn_green": namecom,
        },
        "telegram": {
            "provider": "telegram_evidence_service",
            "method": "channels.checkUsername",
            "scope": "channel",
            "configured": telegram,
            "authoritative_claimability": True,
            "can_turn_green": telegram,
        },
    }
    for resource in ("instagram", "tiktok", "youtube", "facebook", "x"):
        resources[resource] = {
            "provider": None,
            "configured": False,
            "authoritative_claimability": False,
            "can_turn_green": False,
            "reason": "No authoritative username-assignment provider is configured for this platform",
        }
    return {
        "version": "strict-v1",
        "green_status": "claimable",
        "deferred_from_fast_path": deferred_enabled(),
        "resources": resources,
        "configured_green_resources": [key for key, value in resources.items() if value.get("can_turn_green")],
        "unsupported_green_resources": [key for key, value in resources.items() if not value.get("authoritative_claimability")],
        "absence_can_turn_green": False,
        "browser_can_turn_green": False,
        "search_can_turn_green": False,
    }


def configured_strict_resources() -> set[str]:
    caps = strict_claimability_capabilities()["resources"]
    return {key for key in STRICT_RESOURCES if caps.get(key, {}).get("can_turn_green")}


def _status(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "unknown"
    return str(payload.get("status") or "unknown").lower()


def strict_resources_to_probe(row: dict[str, Any], required_resources=None) -> list[str]:
    if not isinstance(row, dict) or not row.get("name"):
        return []
    availability_map = row.get("availability") if isinstance(row.get("availability"), dict) else {}
    required = list(required_resources or row.get("required_resources") or availability_map.keys())
    configured = configured_strict_resources()
    if not configured:
        return []
    if any(_status(availability_map.get(resource)) in HARD_CONFLICT for resource in required):
        return []
    return [
        resource for resource in required
        if resource in configured
        and resource in availability_map
        and _status(availability_map.get(resource)) in PROBEABLE_STATUSES
    ]


def _fast_check_com(name: str):
    """RDAP-only foreground .com check used when strict confirmation is deferred."""
    domain = f"{str(name).lower()}.com"
    public_url = f"https://{domain}"
    rdap_url = f"https://rdap.verisign.com/com/v1/domain/{quote(domain)}"
    try:
        response = requests.get(
            rdap_url,
            timeout=availability.HTTP_TIMEOUT,
            headers={"User-Agent": availability.USER_AGENT},
        )
    except requests.RequestException as error:
        return availability._result("unknown", f"RDAP error: {type(error).__name__}", public_url)
    if response.status_code == 200:
        return availability._result(
            "taken",
            "Registered in .com RDAP",
            public_url,
            source="verisign_rdap",
            method="rdap_exact_domain",
            confidence=0.99,
            occupancy="occupied",
            claimability="not_claimable",
        )
    if response.status_code == 404:
        return availability._result(
            "not_found",
            "Not found in .com RDAP; authoritative registrar confirmation is queued",
            public_url,
            source="verisign_rdap",
            method="rdap_exact_domain",
            confidence=0.9,
            occupancy="not_found",
        )
    return availability._result("unknown", f"RDAP HTTP {response.status_code}", public_url)


def install_fast_path_deference() -> bool:
    """Keep expensive strict providers off the foreground verifier when enabled."""
    if not deferred_enabled():
        return False
    availability.check_com = _fast_check_com
    # telegram_integration captured the original public checker before installing
    # the evidence-backed replacement, so this is a clean public-only fast path.
    availability.check_telegram = telegram_integration._PUBLIC_CHECKER
    return True


def _probe_com(name: str):
    return availability._check_namecom_registration(f"{str(name).lower()}.com")


def _probe_telegram(name: str):
    envelope = fetch_telegram_evidence(str(name), timeout=availability.HTTP_TIMEOUT)
    if envelope is None:
        return None
    return telegram_integration.classify_telegram_evidence(str(name), envelope)


def probe_strict_resource(name: str, resource: str):
    resource = str(resource or "").lower()
    if resource == "com":
        return _probe_com(name)
    if resource == "telegram":
        return _probe_telegram(name)
    return None


def _compact_probe(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"status": "unknown", "authoritative": False}
    compact = {
        key: row.get(key)
        for key in ("status", "detail", "source", "method", "confidence", "occupancy", "claimability", "checked_at", "url", "offer")
        if key in row
    }
    compact["authoritative"] = _status(row) in DECISIVE_STRICT_STATUSES
    return compact


def _bundle_fields(row: dict[str, Any], required_resources) -> dict[str, Any]:
    availability_map = row.get("availability") if isinstance(row.get("availability"), dict) else {}
    required = [str(item) for item in (required_resources or availability_map.keys()) if str(item) in availability_map]
    bundle = classify_identity_bundle(availability_map, required)
    statuses = {resource: _status(availability_map.get(resource)) for resource in required}
    bundle.update({
        "bundle_availability_state": strict_availability_state(availability_map, required),
        "bundle_claimable": [resource for resource, status in statuses.items() if status == "claimable"],
        "bundle_purchasable": [resource for resource, status in statuses.items() if status == "purchasable"],
    })
    return bundle


def apply_strict_claimability(row: dict[str, Any], required_resources=None) -> dict[str, Any]:
    """Run sparse authoritative probes and refresh the candidate ranking.

    Provider failure never erases already useful absence evidence. Only a
    decisive authoritative result may rewrite availability; unknown/rate-limit
    outcomes are kept as audit metadata and the candidate stays non-green.
    """
    result = deepcopy(row or {})
    availability_map = dict(result.get("availability") or {})
    required = list(required_resources or result.get("required_resources") or availability_map.keys())
    resources = strict_resources_to_probe(result, required)
    meta = dict(result.get("strict_claimability") or {})

    if resources:
        workers = max(1, min(2, len(resources)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="strict-claimability") as executor:
            futures = {executor.submit(probe_strict_resource, result.get("name"), resource): resource for resource in resources}
            for future in as_completed(futures):
                resource = futures[future]
                try:
                    strict_row = future.result()
                except Exception as error:
                    strict_row = {
                        "status": "unknown",
                        "detail": f"Strict claimability probe failed: {type(error).__name__}",
                        "source": "strict_claimability",
                        "method": "provider_error",
                        "confidence": 0.0,
                        "claimability": "unconfirmed",
                    }
                meta[resource] = _compact_probe(strict_row)
                if isinstance(strict_row, dict) and _status(strict_row) in DECISIVE_STRICT_STATUSES:
                    availability_map[resource] = strict_row

    caps = strict_claimability_capabilities()["resources"]
    unprovable = [
        resource for resource in required
        if resource in caps and not caps[resource].get("authoritative_claimability")
    ]
    configured = [resource for resource in required if caps.get(resource, {}).get("can_turn_green")]
    result["availability"] = availability_map
    result["strict_claimability"] = meta
    result["strict_claimability_state"] = (
        "complete" if configured and all(resource in meta or _status(availability_map.get(resource)) in DECISIVE_STRICT_STATUSES for resource in configured)
        else "unavailable" if not configured
        else "partial"
    )
    result["strict_claimability_unprovable_required"] = unprovable
    result.update(_bundle_fields(result, required))
    result.update(annotate_candidate(result, required))
    return result


def _same_run(existing: dict[str, Any], incoming: dict[str, Any]) -> bool:
    existing_run = str(existing.get("run_id") or "")
    incoming_run = str(incoming.get("run_id") or "")
    return not (existing_run and incoming_run and existing_run != incoming_run)


def install_runtime_overlay() -> None:
    """Attach strict claimability after Browser Intelligence without editing its hot path."""
    import browser_enrichment
    import browser_queue

    # Expand durable queue admission so .com/Telegram strict-only work is not lost
    # when no browserable social resource is selected.
    base_candidate = browser_queue._browser_candidate
    if not getattr(base_candidate, "_strict_claimability_wrapper", False):
        def candidate(row):
            if base_candidate(row):
                return True
            if not isinstance(row, dict) or row.get("checked") is not True or not row.get("name"):
                return False
            if str(row.get("product_mode") or "") == "generic_name":
                return False
            if str(row.get("strict_claimability_state") or "") == "complete":
                return False
            availability_map = row.get("availability") if isinstance(row.get("availability"), dict) else {}
            required = list(row.get("required_resources") or availability_map.keys())
            return bool(strict_resources_to_probe(row, required))
        candidate._strict_claimability_wrapper = True
        browser_queue._browser_candidate = candidate

    # Completed strict provider facts are server-side evidence just like Browser
    # Eye facts. A stale same-run localStorage mirror must never erase a green
    # registrar/Telegram result after it has been persisted.
    base_merge = browser_queue.BrowserJobQueue._merge_existing_browser
    if not getattr(base_merge, "_strict_claimability_wrapper", False):
        def merge_server_facts(existing, incoming):
            merged = base_merge(existing, incoming)
            if not isinstance(existing, dict) or not isinstance(incoming, dict):
                return merged
            if not _same_run(existing, incoming):
                return merged
            strict_state = str(existing.get("strict_claimability_state") or "")
            strict_meta = existing.get("strict_claimability")
            if strict_state not in {"complete", "partial"} or not isinstance(strict_meta, dict) or not strict_meta:
                return merged
            protected = dict(merged) if isinstance(merged, dict) else dict(incoming)
            if isinstance(existing.get("availability"), dict):
                protected["availability"] = existing["availability"]
            for key in STRICT_SERVER_KEYS:
                if key in existing:
                    protected[key] = existing[key]
            return protected
        merge_server_facts._strict_claimability_wrapper = True
        browser_queue.BrowserJobQueue._merge_existing_browser = staticmethod(merge_server_facts)

    # Every browser persistence now passes through strict claimability first. This
    # makes browser evidence + authoritative probe one durable final update.
    base_persist = browser_enrichment.persist_browser_enrichment
    if not getattr(base_persist, "_strict_claimability_wrapper", False):
        def strict_persist(event_store, job, enriched_row, stage="browser_v3"):
            required = job.get("required_resources") or job.get("resources") or []
            enriched_row = apply_strict_claimability(enriched_row, required)
            return base_persist(event_store, job, enriched_row, stage="strict_claimability_v1")
        strict_persist._strict_claimability_wrapper = True
        browser_enrichment.persist_browser_enrichment = strict_persist

    # .com-only and Telegram-only strict candidates can have no browser work. The
    # original runtime returns None in that case; finish the strict stage directly.
    base_run = browser_enrichment.BrowserEnrichmentRuntime._run
    if not getattr(base_run, "_strict_claimability_wrapper", False):
        def strict_run(self, job, row, event_store):
            outcome = base_run(self, job, row, event_store)
            if outcome is not None:
                return outcome
            required = job.get("required_resources") or job.get("resources") or []
            if not strict_resources_to_probe(row, required):
                return None
            enriched = apply_strict_claimability(row, required)
            return base_persist(event_store, job, enriched, stage="strict_claimability_v1")
        strict_run._strict_claimability_wrapper = True
        browser_enrichment.BrowserEnrichmentRuntime._run = strict_run


def install_strict_claimability() -> dict[str, Any]:
    install_fast_path_deference()
    install_runtime_overlay()
    return strict_claimability_capabilities()


__all__ = [
    "apply_strict_claimability",
    "configured_strict_resources",
    "deferred_enabled",
    "install_fast_path_deference",
    "install_runtime_overlay",
    "install_strict_claimability",
    "probe_strict_resource",
    "strict_claimability_capabilities",
    "strict_resources_to_probe",
]
