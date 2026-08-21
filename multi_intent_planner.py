"""Bounded multi-intent planning for Universal Search.

The planner composes already-existing research modules. It does not change the
truth semantics of those modules and never upgrades retrieval evidence into
verified facts.
"""
from __future__ import annotations

import re

from intelligence_modules import (
    LOCAL_INFORMATION_GUARD,
    MODULES,
    PRODUCT_FINANCE_GUARD,
)


MAX_MULTI_ROUTES = 3
MULTI_ROUTE_PAIRS = {
    frozenset(("product", "local")),
    frozenset(("product", "news")),
    frozenset(("local", "news")),
    frozenset(("technical", "news")),
    frozenset(("company", "news")),
    frozenset(("person", "news")),
}

_LOCAL_COMMERCE_CUES = (
    r"\bwhere to buy\b",
    r"\bpickup\b",
    r"\bclick and collect\b",
    r"\bде купити\b",
    r"\bсамовивіз\w*\b",
    r"\bgdzie kupić\b",
    r"\bodbiór osobisty\b",
)
_LOCAL_GEOGRAPHY_CUES = (
    r"\b(?:in|near)\s+(?!stock\b|store\b|stores\b|the\b|a\b|an\b|this\b|that\b|general\b)[\wÀ-ž.-]{2,}\b",
    r"\b(?:у|в|біля)\s+(?!наявност\w*\b|магазин\w*\b)[\wА-Яа-яІіЇїЄєҐґ.-]{2,}\b",
    r"\b(?:w|koło|obok|blisko)\s+(?!magazyn\w*\b|sklep\w*\b)[\wÀ-ž.-]{2,}\b",
)


def _clean_query(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _module_score(module, text: str) -> int:
    score = 0
    for pattern, weight in module.patterns:
        matches = re.findall(pattern, text, flags=re.I)
        if matches:
            score += weight * min(2, len(matches))
    return score


def _module_is_guarded(module, text: str) -> bool:
    if module.name == "local" and LOCAL_INFORMATION_GUARD.search(text):
        return True
    if module.name == "product" and PRODUCT_FINANCE_GUARD.search(text):
        return True
    return False


def classify_module_candidates(query: object) -> list[dict]:
    """Return every high-confidence module candidate in deterministic order."""
    cleaned = _clean_query(query)
    text = cleaned.casefold()
    candidates = []
    for module in MODULES:
        if _module_is_guarded(module, text):
            continue
        score = _module_score(module, text)
        if score < module.threshold:
            continue
        candidates.append({
            "route": module.name,
            "score": score,
            "threshold": module.threshold,
            "priority": module.priority,
            "confidence": min(100, 55 + score * 7),
            "module_version": module.version,
            "reason": "high_confidence_research_module",
        })
    candidates.sort(
        key=lambda item: (
            -int(item["score"]),
            -int(item["priority"]),
            str(item["route"]),
        )
    )
    return candidates


def _has_local_commerce_context(query: str) -> bool:
    has_commerce = any(
        re.search(pattern, query, flags=re.I) for pattern in _LOCAL_COMMERCE_CUES
    )
    has_geography = any(
        re.search(pattern, query, flags=re.I) for pattern in _LOCAL_GEOGRAPHY_CUES
    )
    return bool(has_commerce and has_geography)


def _compatible(route: str, selected: list[str]) -> bool:
    return all(
        frozenset((route, existing)) in MULTI_ROUTE_PAIRS for existing in selected
    )


def plan_research_routes(query: object) -> dict:
    """Build a bounded compatible route set while preserving a single primary lane."""
    cleaned = _clean_query(query)
    candidates = classify_module_candidates(cleaned)

    routes_present = {item["route"] for item in candidates}
    if (
        "product" in routes_present
        and "local" not in routes_present
        and _has_local_commerce_context(cleaned)
    ):
        local = next(module for module in MODULES if module.name == "local")
        candidates.append({
            "route": "local",
            "score": local.threshold,
            "threshold": local.threshold,
            "priority": local.priority,
            "confidence": min(100, 55 + local.threshold * 7),
            "module_version": local.version,
            "reason": "composite_local_commerce_intent",
        })
        candidates.sort(
            key=lambda item: (
                -int(item["score"]),
                -int(item["priority"]),
                str(item["route"]),
            )
        )

    selected: list[dict] = []
    for candidate in candidates:
        route = str(candidate["route"])
        if not selected:
            selected.append(candidate)
            continue
        if len(selected) >= MAX_MULTI_ROUTES:
            break
        selected_routes = [str(item["route"]) for item in selected]
        if _compatible(route, selected_routes):
            selected.append(candidate)

    routes = [str(item["route"]) for item in selected]
    return {
        "routes": routes,
        "primary_route": routes[0] if routes else "general_web",
        "multi_intent": len(routes) > 1,
        "reason": "multi_intent_research_modules" if len(routes) > 1 else (
            selected[0]["reason"] if selected else "no_specialized_research_module"
        ),
        "module_confidence": int(selected[0]["confidence"]) if selected else 0,
        "module_version": selected[0]["module_version"] if len(selected) == 1 else (
            "multi-intent-v1" if selected else None
        ),
        "module_versions": {
            str(item["route"]): item["module_version"] for item in selected
        },
        "candidates": candidates,
    }


def multi_intent_capabilities() -> dict:
    pairs = sorted(sorted(pair) for pair in MULTI_ROUTE_PAIRS)
    return {
        "version": "multi-intent-v1",
        "max_routes": MAX_MULTI_ROUTES,
        "shared_exact_query": True,
        "max_provider_queries": 1 + MAX_MULTI_ROUTES,
        "compatible_route_pairs": pairs,
        "truth_semantics": "retrieval_evidence_not_verified_fact",
    }


__all__ = [
    "MAX_MULTI_ROUTES",
    "MULTI_ROUTE_PAIRS",
    "classify_module_candidates",
    "multi_intent_capabilities",
    "plan_research_routes",
]
