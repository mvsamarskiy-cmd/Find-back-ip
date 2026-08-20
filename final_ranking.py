"""Transparent final candidate ranking for NameMachine.

The generator, taste learner, and availability verifier answer different questions.
This module keeps those signals separate and combines them only at the final
ranking boundary. Semantic truth is never inferred from a score: only direct
`claimable` evidence is strict free availability, while `purchasable`,
`not_found`, conflicts, and unresolved evidence remain distinct states.
"""
from __future__ import annotations

import re
from functools import wraps

from candidate_funnel import (
    LOCAL_SOURCE,
    linguistic_quality as legacy_linguistic_quality,
    structural_quality as legacy_structural_quality,
)


CONFLICT_STATUSES = frozenset({"taken", "reserved", "invalid"})
UNRESOLVED_STATUSES = frozenset({"unknown", "rate_limited", "available"})
ACTIONABLE_STATUSES = frozenset({"claimable", "purchasable"})

OPPORTUNITY_UTILITY = {
    "claimable": 1.00,
    "purchasable": 0.82,
    "not_found": 0.55,
    "unknown": 0.18,
    "rate_limited": 0.14,
    "available": 0.18,  # legacy ambiguous status; never treated as free
    "taken": 0.0,
    "reserved": 0.0,
    "invalid": 0.0,
}


def _clamp(value, low=0.0, high=100.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def _letters(value):
    return re.sub(r"[^a-z]", "", str(value or "").lower())


def _name_segments(value):
    """Preserve explicit word boundaries before normalizing to letters.

    `DawnFlock` contains a real Dawn|Flock boundary. Legacy structural scoring
    lowercased first and saw an artificial `wnfl` four-consonant run. We score
    both the whole identifier and explicit segments so meaningful compounds are
    not punished for consonants that only meet across a morpheme boundary.
    """
    raw = str(value or "").strip()
    if not raw:
        return []
    separated = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw)
    parts = [
        _letters(part)
        for part in re.split(r"[^A-Za-z]+", separated)
        if _letters(part)
    ]
    return parts or ([_letters(raw)] if _letters(raw) else [])


def _weighted_segment_score(segments, scorer):
    total = sum(len(part) for part in segments)
    if not total:
        return 0.0
    return sum(scorer(part) * len(part) for part in segments) / total


def structural_quality_score(name):
    whole = float(legacy_structural_quality(name))
    segments = _name_segments(name)
    if len(segments) <= 1:
        return round(whole, 1)
    segmented = _weighted_segment_score(segments, legacy_structural_quality)
    return round(max(whole, 0.42 * whole + 0.58 * segmented), 1)


def linguistic_quality_score(name):
    whole = float(legacy_linguistic_quality(name))
    segments = _name_segments(name)
    if len(segments) <= 1:
        return round(whole, 1)
    segmented = _weighted_segment_score(segments, legacy_linguistic_quality)
    return round(max(whole, 0.35 * whole + 0.65 * segmented), 1)


def name_quality_score(name, candidate_source=None):
    structural = structural_quality_score(name)
    linguistic = linguistic_quality_score(name)
    score = 0.56 * structural + 0.44 * linguistic
    if candidate_source == LOCAL_SOURCE:
        score -= 6.0
    return round(_clamp(score), 1)


def rank_candidate_pool_v2(candidates):
    """Drop-in pre-verification ranker with auditable quality dimensions."""
    ranked = []
    for index, candidate in enumerate(candidates or []):
        if not isinstance(candidate, dict):
            continue
        row = dict(candidate)
        structural = structural_quality_score(row.get("name", ""))
        linguistic = linguistic_quality_score(row.get("name", ""))
        quality = name_quality_score(row.get("name", ""), row.get("candidate_source"))
        row["structural_quality_score"] = structural
        row["linguistic_quality_score"] = linguistic
        row["name_quality_score"] = quality
        # Existing selectors read this compatibility field. In production it now
        # means the combined pre-check quality rather than structural shape alone.
        row["local_quality_score"] = quality
        ranked.append((index, row))
    ranked.sort(key=lambda item: (-item[1]["name_quality_score"], item[0]))
    return [row for _index, row in ranked]


def _status(result):
    if not isinstance(result, dict):
        return "unknown"
    status = str(result.get("status") or "unknown").lower()
    return status if status in OPPORTUNITY_UTILITY else "unknown"


def _required_resources(row, required_resources=None):
    availability = row.get("availability") if isinstance(row, dict) else None
    availability = availability if isinstance(availability, dict) else {}
    requested = required_resources
    if requested is None and isinstance(row, dict):
        requested = row.get("required_resources")
    if isinstance(requested, (list, tuple)):
        result = [str(key) for key in requested if str(key) in availability]
        if result:
            return result
    return list(availability.keys())


def strict_availability_state(availability, required_resources=None):
    """Return the truthful decision state without collapsing paid/free states."""
    rows = availability if isinstance(availability, dict) else {}
    required = list(required_resources or rows.keys())
    if not required:
        return "unverified"
    statuses = [_status(rows.get(resource)) for resource in required]
    if any(status in CONFLICT_STATUSES for status in statuses):
        return "conflict"
    if any(status in UNRESOLVED_STATUSES for status in statuses):
        return "unresolved"
    if all(status == "claimable" for status in statuses):
        return "claimable"
    if any(status == "not_found" for status in statuses):
        return "promising"
    if all(status in ACTIONABLE_STATUSES for status in statuses) and any(
        status == "purchasable" for status in statuses
    ):
        return "purchasable"
    return "unresolved"


def availability_metrics(row, required_resources=None):
    availability = row.get("availability") if isinstance(row, dict) else None
    availability = availability if isinstance(availability, dict) else {}
    required = _required_resources(row if isinstance(row, dict) else {}, required_resources)
    state = strict_availability_state(availability, required)
    if not required:
        return {
            "availability_state": "unverified",
            "availability_opportunity_score": None,
            "availability_evidence_confidence_score": None,
            "verification_coverage_score": 0.0,
        }

    utilities = []
    confidences = []
    resolved = 0
    for resource in required:
        evidence = availability.get(resource)
        status = _status(evidence)
        utilities.append(OPPORTUNITY_UTILITY.get(status, OPPORTUNITY_UTILITY["unknown"]))
        if isinstance(evidence, dict):
            confidences.append(_clamp(evidence.get("confidence", 0.5), 0.0, 1.0))
        else:
            confidences.append(0.0)
        if status not in UNRESOLVED_STATUSES:
            resolved += 1

    opportunity = round(sum(utilities) / len(utilities) * 100, 1)
    confidence = round(sum(confidences) / len(confidences) * 100, 1)
    coverage = round(resolved / len(required) * 100, 1)
    return {
        "availability_state": state,
        "availability_opportunity_score": opportunity,
        "availability_evidence_confidence_score": confidence,
        "verification_coverage_score": coverage,
    }


def _identity_score(quality, user_fit, adaptive_relevance, has_user_fit):
    if adaptive_relevance is not None:
        adaptive = _clamp(adaptive_relevance)
        return 0.45 * quality + 0.55 * adaptive
    if has_user_fit:
        return 0.68 * quality + 0.32 * user_fit
    return quality


def _state_penalty(state):
    return {
        "claimable": 0.0,
        "purchasable": -1.5,
        "promising": 0.0,
        "unresolved": -5.0,
        "conflict": -18.0,
        "unverified": 0.0,
    }.get(state, -5.0)


def _reason_text(quality, user_fit, availability_state, opportunity):
    parts = [f"якість назви {round(quality):.0f}/100"]
    if user_fit is not None:
        parts.append(f"відповідність смаку {round(user_fit):.0f}/100")
    state_copy = {
        "claimable": "вільність підтверджена",
        "purchasable": "доступно лише через купівлю",
        "promising": "є позитивні ознаки, але claimability не підтверджена",
        "unresolved": "перевірка доступності неповна",
        "conflict": "є підтверджений конфлікт",
        "unverified": "доступність не перевірялась",
    }
    parts.append(state_copy.get(availability_state, "стан доступності невизначений"))
    if opportunity is not None:
        parts.append(f"можливість {round(opportunity):.0f}/100")
    return " · ".join(parts)


def annotate_candidate(row, required_resources=None):
    """Attach independent ranking dimensions and one transparent final score."""
    if not isinstance(row, dict):
        return {}
    quality = _clamp(
        row.get("name_quality_score")
        if row.get("name_quality_score") is not None
        else name_quality_score(row.get("name", ""), row.get("candidate_source"))
    )
    structural = _clamp(
        row.get("structural_quality_score")
        if row.get("structural_quality_score") is not None
        else structural_quality_score(row.get("name", ""))
    )
    linguistic = _clamp(
        row.get("linguistic_quality_score")
        if row.get("linguistic_quality_score") is not None
        else linguistic_quality_score(row.get("name", ""))
    )

    has_user_fit = row.get("user_fit_score") is not None
    user_fit = _clamp(row.get("user_fit_score", 50.0)) if has_user_fit else None
    adaptive = row.get("adaptive_relevance_score")
    adaptive_value = _clamp(adaptive) if adaptive is not None else None
    identity = _identity_score(
        quality,
        user_fit if user_fit is not None else 50.0,
        adaptive_value,
        has_user_fit,
    )

    availability = availability_metrics(row, required_resources)
    opportunity = availability["availability_opportunity_score"]
    state = availability["availability_state"]
    if opportunity is None:
        final = identity
    else:
        # Naming/taste stays the dominant component. Availability affects decision
        # rank but cannot turn a poor name into a strong name merely because a
        # checker found no conflict.
        final = 0.72 * identity + 0.28 * opportunity + _state_penalty(state)

    final = round(_clamp(final), 1)
    return {
        "structural_quality_score": round(structural, 1),
        "linguistic_quality_score": round(linguistic, 1),
        "name_quality_score": round(quality, 1),
        "user_fit_score": round(user_fit, 1) if user_fit is not None else 50.0,
        "identity_relevance_score": round(_clamp(identity), 1),
        **availability,
        "final_score": final,
        "ranking_reason": _reason_text(quality, user_fit, state, opportunity),
        "ranking_model": "final-v1",
    }


def _legacy_count_sort_key(row):
    """Preserve the historical count-only contract used by legacy callers/tests.

    Real v2 verification rows carry an `availability` mapping and use final-v1.
    Old generated fixtures may contain only aggregate counts; inventing resource
    evidence from those counts would be epistemically wrong, so retain their old
    deterministic ordering instead of pretending they have v2 evidence.
    """
    if not isinstance(row, dict):
        return None
    availability = row.get("availability")
    count_keys = (
        "claimable_count", "purchasable_count", "not_found_count", "taken_count",
        "reserved_count", "invalid_count", "unresolved_count", "unknown_count",
    )
    if isinstance(availability, dict) and availability:
        return None
    if not any(key in row for key in count_keys):
        return None
    return (
        -row.get("claimable_count", 0),
        -row.get("purchasable_count", 0),
        -row.get("not_found_count", 0),
        row.get("taken_count", 0) + row.get("reserved_count", 0) + row.get("invalid_count", 0),
        row.get("unresolved_count", row.get("unknown_count", 0)),
        -row.get("score", 0),
        row.get("length", len(row.get("name", ""))),
        row.get("name", "").lower(),
    )


def final_ranking_sort_key(row):
    legacy = _legacy_count_sort_key(row)
    if legacy is not None:
        return legacy
    ranking = annotate_candidate(row)
    if isinstance(row, dict):
        row.update(ranking)
    opportunity = ranking.get("availability_opportunity_score")
    return (
        -float(ranking.get("final_score", 0.0)),
        -float(ranking.get("identity_relevance_score", 0.0)),
        -float(opportunity if opportunity is not None else -1.0),
        -float(ranking.get("name_quality_score", 0.0)),
        str((row or {}).get("name", "")).lower(),
    )


def _strict_bundle_fields(availability, required_resources):
    rows = availability if isinstance(availability, dict) else {}
    required = list(required_resources or [])
    statuses = {resource: _status(rows.get(resource)) for resource in required}
    return {
        "bundle_availability_state": strict_availability_state(rows, required),
        "bundle_claimable": [key for key, status in statuses.items() if status == "claimable"],
        "bundle_purchasable": [key for key, status in statuses.items() if status == "purchasable"],
    }


def install_final_ranking(app_module, *, ai_module=None, generic_module=None, streaming_module=None):
    """Install ranking at existing runtime seams without changing API routes."""
    if getattr(app_module, "_FINAL_RANKING_INSTALLED", False):
        return

    base_classify = app_module.classify_identity_bundle

    @wraps(base_classify)
    def classify_with_strict_state(availability, required_resources):
        result = dict(base_classify(availability, required_resources))
        result.update(_strict_bundle_fields(availability, required_resources))
        return result

    app_module.classify_identity_bundle = classify_with_strict_state
    app_module.availability_sort_key = final_ranking_sort_key
    app_module.annotate_candidate_ranking = annotate_candidate

    if ai_module is not None:
        ai_module.rank_candidate_pool = rank_candidate_pool_v2

    if generic_module is not None:
        generic_module.rank_candidate_pool = rank_candidate_pool_v2
        base_generate = generic_module.generate_generic_names
        if not getattr(base_generate, "_final_ranking_wrapper", False):
            @wraps(base_generate)
            def generate_with_scores(*args, **kwargs):
                rows = base_generate(*args, **kwargs)
                for row in rows if isinstance(rows, list) else []:
                    if isinstance(row, dict):
                        row.update(annotate_candidate(row))
                return rows
            generate_with_scores._final_ranking_wrapper = True
            generic_module.generate_generic_names = generate_with_scores

    if streaming_module is not None:
        base_finalize = streaming_module._finalize_candidate
        if not getattr(base_finalize, "_final_ranking_wrapper", False):
            @wraps(base_finalize)
            def finalize_with_ranking(app_mod, source_row, resources, required_resources, parts):
                row = base_finalize(app_mod, source_row, resources, required_resources, parts)
                row.update(annotate_candidate(row, required_resources))
                return row
            finalize_with_ranking._final_ranking_wrapper = True
            streaming_module._finalize_candidate = finalize_with_ranking

    app_module._FINAL_RANKING_INSTALLED = True


__all__ = [
    "annotate_candidate",
    "availability_metrics",
    "final_ranking_sort_key",
    "install_final_ranking",
    "linguistic_quality_score",
    "name_quality_score",
    "rank_candidate_pool_v2",
    "strict_availability_state",
    "structural_quality_score",
]
