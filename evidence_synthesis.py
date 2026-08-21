"""Deterministic evidence synthesis for Universal Search.

This layer summarizes retrieval evidence without upgrading snippets, listings,
or preferred-source matches into verified facts. Observations always retain
source provenance and conflicts remain explicit candidates for verification.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re


SYNTHESIS_VERSION = "evidence-synthesis-v1"
MAX_TOP_EVIDENCE = 12
MAX_OBSERVATIONS = 40

_CURRENCY_ALIASES = {
    "€": "EUR", "eur": "EUR", "euro": "EUR",
    "$": "USD", "usd": "USD", "dollar": "USD", "dollars": "USD",
    "£": "GBP", "gbp": "GBP", "pound": "GBP", "pounds": "GBP",
    "zł": "PLN", "zl": "PLN", "pln": "PLN",
}
_CURRENCY_RE = re.compile(
    r"(?:(?P<prefix>€|\$|£|PLN|EUR|USD|GBP|zł|zl)\s*"
    r"(?P<num1>\d{1,3}(?:[\s.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?))"
    r"|(?:(?P<num2>\d{1,3}(?:[\s.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*"
    r"(?P<suffix>PLN|EUR|USD|GBP|euro|zł|zl|dollars?|pounds?))",
    flags=re.I,
)

_AVAILABILITY_MARKERS = (
    ("unavailable", re.compile(r"\b(?:out of stock|sold out|unavailable|brak w magazynie|niedostępn\w*|wyprzedan\w*|немає в наявності|відсутн\w*)\b", re.I)),
    ("available", re.compile(r"\b(?:in stock|available now|available|dostępn\w*|w magazynie|в наявності|доступн\w*)\b", re.I)),
)
_LOCAL_STATUS_MARKERS = (
    ("closed", re.compile(r"\b(?:closed now|currently closed|zamknięt\w* teraz|zamknięt\w*|зачинен\w* зараз|закрит\w* зараз)\b", re.I)),
    ("open", re.compile(r"\b(?:open now|currently open|otwarte teraz|otwart\w* teraz|відкрит\w* зараз)\b", re.I)),
)


def _clean(value: object, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def _parse_number(raw: object) -> float | None:
    text = str(raw or "").replace("\u00a0", " ").replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif text.count(",") == 1:
        left, right = text.split(",", 1)
        text = left + "." + right if len(right) <= 2 else left + right
    elif text.count(".") == 1:
        left, right = text.split(".", 1)
        if len(right) == 3 and len(left) >= 1:
            text = left + right
    try:
        value = float(text)
    except ValueError:
        return None
    if value < 0:
        return None
    return round(value, 2)


def _currency_observations(text: str, *, max_items: int = 3) -> list[dict]:
    observations = []
    seen = set()
    for match in _CURRENCY_RE.finditer(text):
        raw_currency = match.group("prefix") or match.group("suffix") or ""
        currency = _CURRENCY_ALIASES.get(raw_currency.casefold(), _CURRENCY_ALIASES.get(raw_currency))
        value = _parse_number(match.group("num1") or match.group("num2"))
        if not currency or value is None:
            continue
        signature = (currency, value)
        if signature in seen:
            continue
        seen.add(signature)
        observations.append({
            "currency": currency,
            "value": value,
            "evidence": _clean(match.group(0), 120),
        })
        if len(observations) >= max_items:
            break
    return observations


def _row_routes(row: dict, fallback_routes: list[str]) -> list[str]:
    raw = row.get("intelligence_routes")
    if not isinstance(raw, list):
        raw = row.get("evidence_lanes")
    routes = []
    for value in raw if isinstance(raw, list) else fallback_routes:
        route = _clean(value, 80).lower()
        if route and route != "shared" and route not in routes:
            routes.append(route)
    if not routes:
        primary = _clean(row.get("intelligence_route"), 80).lower()
        if primary:
            routes.append(primary)
    return routes


def _verification_state(row: dict) -> dict:
    verification = row.get("verification")
    explicit_verified = row.get("verified") is True
    state = "unverified_retrieval_evidence"
    detail = None
    if isinstance(verification, dict):
        explicit_verified = explicit_verified or verification.get("verified") is True
        raw_state = verification.get("state") or verification.get("status") or verification.get("value")
        if raw_state:
            detail = _clean(raw_state, 80)
    elif isinstance(verification, str) and verification.strip():
        detail = _clean(verification, 80)
    if explicit_verified:
        state = "explicitly_verified_by_upstream"
    return {
        "state": state,
        "upstream_detail": detail,
        "official_source": bool(row.get("official_source")),
        "independently_verified": bool(explicit_verified),
    }


def _freshness(row: dict, retrieved_at: str) -> dict:
    published = (
        row.get("published_at")
        or row.get("published_date")
        or row.get("source_published_at")
        or row.get("date")
    )
    published_text = _clean(published, 80) if published else None
    return {
        "retrieved_at": retrieved_at,
        "source_published_at": published_text,
        "basis": "source_date_plus_retrieval_time" if published_text else "retrieval_time_only",
    }


def _source_record(row: dict, *, fallback_routes: list[str], retrieved_at: str) -> dict:
    lanes = row.get("evidence_lanes") if isinstance(row.get("evidence_lanes"), list) else []
    return {
        "title": _clean(row.get("title"), 300),
        "url": _clean(row.get("url"), 1000),
        "host": _clean(row.get("host") or row.get("source_name"), 200).lower(),
        "excerpt": _clean(row.get("description"), 360),
        "retrieval_score": int(row.get("retrieval_score") or row.get("score") or 0),
        "routes": _row_routes(row, fallback_routes),
        "evidence_lanes": [_clean(item, 80) for item in lanes[:8]],
        "preferred_source_match": bool(row.get("preferred_source_match")),
        "verification": _verification_state(row),
        "freshness": _freshness(row, retrieved_at),
    }


def _observations_for_source(source: dict, *, routes: list[str], retrieved_at: str) -> list[dict]:
    text = f"{source['title']} {source['excerpt']}"
    observations = []
    row_routes = source.get("routes") or routes
    monetary_kind = "price_mention" if "product" in row_routes else "amount_mention"
    for amount in _currency_observations(text):
        observations.append({
            "type": monetary_kind,
            "status": "retrieval_observation",
            "currency": amount["currency"],
            "value": amount["value"],
            "evidence": amount["evidence"],
            "source_url": source["url"],
            "source_host": source["host"],
            "routes": list(row_routes),
            "retrieved_at": retrieved_at,
            "independently_verified": False,
        })

    if "product" in row_routes:
        for value, pattern in _AVAILABILITY_MARKERS:
            match = pattern.search(text)
            if match:
                observations.append({
                    "type": "availability_mention",
                    "status": "retrieval_observation",
                    "value": value,
                    "evidence": _clean(match.group(0), 120),
                    "source_url": source["url"],
                    "source_host": source["host"],
                    "routes": list(row_routes),
                    "retrieved_at": retrieved_at,
                    "independently_verified": False,
                })
                break

    if "local" in row_routes:
        for value, pattern in _LOCAL_STATUS_MARKERS:
            match = pattern.search(text)
            if match:
                observations.append({
                    "type": "opening_status_mention",
                    "status": "retrieval_observation",
                    "value": value,
                    "evidence": _clean(match.group(0), 120),
                    "source_url": source["url"],
                    "source_host": source["host"],
                    "routes": list(row_routes),
                    "retrieved_at": retrieved_at,
                    "independently_verified": False,
                })
                break
    return observations


def _conflict_candidates(observations: list[dict]) -> list[dict]:
    conflicts = []
    monetary = {}
    for obs in observations:
        if obs.get("type") not in {"price_mention", "amount_mention"}:
            continue
        currency = obs.get("currency")
        if currency:
            monetary.setdefault(currency, []).append(obs)
    for currency, rows in sorted(monetary.items()):
        values = sorted({float(row["value"]) for row in rows if row.get("value") is not None})
        hosts = sorted({row.get("source_host") for row in rows if row.get("source_host")})
        if len(values) >= 2 and len(hosts) >= 2:
            conflicts.append({
                "kind": "price_or_amount_variance",
                "status": "possible_conflict_needs_verification",
                "currency": currency,
                "observed_values": values[:12],
                "source_hosts": hosts[:12],
                "reason": (
                    "Different monetary values were observed across retrieval evidence. "
                    "They may reflect variants, sellers, dates, or genuinely conflicting claims."
                ),
            })

    for obs_type, kind in (
        ("availability_mention", "availability_status_variance"),
        ("opening_status_mention", "opening_status_variance"),
    ):
        rows = [obs for obs in observations if obs.get("type") == obs_type]
        values = sorted({str(obs.get("value")) for obs in rows if obs.get("value")})
        hosts = sorted({obs.get("source_host") for obs in rows if obs.get("source_host")})
        if len(values) >= 2 and len(hosts) >= 2:
            conflicts.append({
                "kind": kind,
                "status": "possible_conflict_needs_verification",
                "observed_values": values,
                "source_hosts": hosts[:12],
                "reason": "Different status mentions were observed across retrieval evidence.",
            })
    return conflicts


def synthesize_search_payload(payload: object, *, now: datetime | None = None) -> dict:
    """Build an auditable structured answer model from a search payload."""
    data = payload if isinstance(payload, dict) else {}
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    retrieved_at = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    raw_routes = data.get("intelligence_routes")
    routes = []
    for raw in raw_routes if isinstance(raw_routes, list) else [data.get("intelligence_route")]:
        route = _clean(raw, 80).lower()
        if route and route not in routes:
            routes.append(route)
    if not routes:
        routes = ["general_web"]

    raw_results = data.get("results") if isinstance(data.get("results"), list) else []
    sources = [
        _source_record(row, fallback_routes=routes, retrieved_at=retrieved_at)
        for row in raw_results
        if isinstance(row, dict) and row.get("url")
    ]
    sources = sources[:MAX_TOP_EVIDENCE]

    observations = []
    for source in sources:
        observations.extend(_observations_for_source(source, routes=routes, retrieved_at=retrieved_at))
        if len(observations) >= MAX_OBSERVATIONS:
            observations = observations[:MAX_OBSERVATIONS]
            break

    conflicts = _conflict_candidates(observations)
    hosts = sorted({source["host"] for source in sources if source.get("host")})
    preferred = sum(1 for source in sources if source.get("preferred_source_match"))
    verified = sum(
        1 for source in sources
        if source.get("verification", {}).get("independently_verified")
    )
    route_coverage = {}
    for route in routes:
        route_coverage[route] = sum(1 for source in sources if route in source.get("routes", []))

    type_counts = {}
    for obs in observations:
        key = str(obs.get("type") or "unknown")
        type_counts[key] = type_counts.get(key, 0) + 1

    return {
        "version": SYNTHESIS_VERSION,
        "mode": "retrieval_evidence",
        "generated_at": retrieved_at,
        "query": _clean(data.get("query"), 1800),
        "routes": routes,
        "summary": {
            "results_available": len(raw_results),
            "top_evidence_count": len(sources),
            "unique_host_count": len(hosts),
            "observation_count": len(observations),
            "observation_types": type_counts,
            "conflict_candidate_count": len(conflicts),
            "explicitly_verified_source_count": verified,
        },
        "source_coverage": {
            "hosts": hosts,
            "preferred_source_count": preferred,
            "route_coverage": route_coverage,
            "provider": data.get("provider"),
            "provider_status": data.get("provider_status"),
        },
        "top_evidence": sources,
        "observations": observations,
        "conflict_candidates": conflicts,
        "freshness": {
            "retrieved_at": retrieved_at,
            "default_basis": "retrieval_time_only",
            "warning": (
                "Retrieval time is not publication time. Current claims require source-date "
                "or direct-source verification before being treated as fresh facts."
            ),
        },
        "truth_status": {
            "verified_fact_generation": False,
            "retrieval_observations_are_facts": False,
            "conflicts_preserved": True,
            "unknowns_preserved": True,
            "preferred_sources_are_verification": False,
        },
    }


def evidence_synthesis_capabilities() -> dict:
    return {
        "version": SYNTHESIS_VERSION,
        "deterministic": True,
        "max_top_evidence": MAX_TOP_EVIDENCE,
        "max_observations": MAX_OBSERVATIONS,
        "price_mentions": True,
        "availability_mentions": True,
        "opening_status_mentions": True,
        "conflict_candidates": True,
        "freshness_basis": "retrieval_time_with_optional_source_date",
        "truth_semantics": "retrieval_evidence_not_verified_fact",
    }


__all__ = [
    "SYNTHESIS_VERSION",
    "evidence_synthesis_capabilities",
    "synthesize_search_payload",
]
