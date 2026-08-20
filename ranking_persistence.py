"""Bounded persistence bridge for final-ranking metadata.

Session candidate storage has a deliberately narrow whitelist. Ranking metadata is
small and useful for audit/replay, but must not bypass the existing sanitizer or
candidate byte budget. This wrapper re-attaches only explicit numeric/state fields
and a bounded human-readable reason after the normal candidate sanitizer runs.
"""
from __future__ import annotations

import json
from functools import wraps


NUMERIC_FIELDS = (
    "structural_quality_score",
    "linguistic_quality_score",
    "name_quality_score",
    "user_fit_score",
    "identity_relevance_score",
    "availability_opportunity_score",
    "availability_evidence_confidence_score",
    "verification_coverage_score",
    "final_score",
)
TEXT_FIELDS = {
    "availability_state": 32,
    "bundle_availability_state": 32,
    "ranking_model": 32,
    "ranking_reason": 600,
}
LIST_FIELDS = {
    "bundle_claimable": 16,
    "bundle_purchasable": 16,
}


def _number(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return round(max(0.0, min(100.0, number)), 2)


def _text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _items(value, limit):
    if not isinstance(value, list):
        return None
    output = []
    for item in value[:limit]:
        clean = _text(item, 32)
        if clean and clean not in output:
            output.append(clean)
    return output


def install_ranking_persistence(session_api_module):
    current = session_api_module._clean_candidate
    if getattr(current, "_namemachine_ranking_persistence", False):
        return current
    original = current

    @wraps(original)
    def wrapped(row, app_module):
        clean = original(row, app_module)
        if clean is None or not isinstance(row, dict):
            return clean

        for key in NUMERIC_FIELDS:
            number = _number(row.get(key))
            if number is not None:
                clean[key] = number
        for key, limit in TEXT_FIELDS.items():
            value = _text(row.get(key), limit)
            if value:
                clean[key] = value
        for key, limit in LIST_FIELDS.items():
            value = _items(row.get(key), limit)
            if value is not None:
                clean[key] = value

        encoded = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > session_api_module.MAX_CANDIDATE_BYTES:
            raise ValueError(f"Candidate {clean.get('name', '')} payload is too large")
        return clean

    wrapped._namemachine_ranking_persistence = True
    wrapped._namemachine_original = original
    session_api_module._clean_candidate = wrapped
    return wrapped


__all__ = ["install_ranking_persistence"]
