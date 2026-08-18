from availability import RESOURCE_KEYS, normalize_resources


CONFLICT_STATUSES = frozenset({"taken", "reserved", "invalid"})
CONFIRMED_STATUSES = frozenset({"claimable", "purchasable"})
PROMISING_STATUSES = frozenset({"not_found"})
POSITIVE_STATUSES = CONFIRMED_STATUSES | PROMISING_STATUSES

STATUS_UTILITY = {
    "claimable": 1.0,
    "purchasable": 0.9,
    "not_found": 0.55,
    "unknown": 0.2,
    "rate_limited": 0.15,
    "taken": 0.0,
    "reserved": 0.0,
    "invalid": 0.0,
}


def normalize_required_resources(required_resources, selected_resources):
    """Return a non-empty required subset of the selected resources.

    When omitted, every selected resource remains required for backward
    compatibility. A required resource that is not selected is a client error.
    """
    selected = normalize_resources(selected_resources)
    if required_resources is None:
        return selected
    required = normalize_resources(required_resources)
    outside = [resource for resource in required if resource not in selected]
    if outside:
        raise ValueError(
            "Required resources must also be selected: " + ", ".join(outside)
        )
    return required


def _normalized_status(result):
    status = str(result.get("status", "unknown")) if isinstance(result, dict) else "unknown"
    return "unknown" if status == "available" else status


def _evidence_utility(result):
    """Score one evidence row without upgrading absence into availability."""
    if not isinstance(result, dict):
        return STATUS_UTILITY["unknown"] * 0.75
    status = _normalized_status(result)
    utility = STATUS_UTILITY.get(status, STATUS_UTILITY["unknown"])
    try:
        confidence = float(result.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    # Confidence changes ranking strength, never the semantic status itself.
    confidence_factor = 0.5 + 0.5 * confidence
    return utility * confidence_factor


def _mean_percent(values):
    if not values:
        return None
    return round(sum(values) / len(values) * 100)


def score_identity_bundle(availability, required_resources):
    """Return a deterministic opportunity score for ranking Identity Bundles.

    MUST-HAVE resources dominate the score. Optional resources can improve or
    weaken ranking but can never erase a required conflict. `not_found` receives
    partial credit only: it is useful evidence of absence, not proof that a handle
    can be claimed.
    """
    required = normalize_resources(required_resources)
    rows = availability if isinstance(availability, dict) else {}
    selected = tuple(resource for resource in RESOURCE_KEYS if resource in rows)
    optional = tuple(resource for resource in selected if resource not in required)

    required_values = [_evidence_utility(rows.get(resource)) for resource in required]
    optional_values = [_evidence_utility(rows.get(resource)) for resource in optional]
    required_score = _mean_percent(required_values)
    optional_score = _mean_percent(optional_values)

    required_statuses = [_normalized_status(rows.get(resource)) for resource in required]
    has_conflict = any(status in CONFLICT_STATUSES for status in required_statuses)
    has_unresolved = any(
        status not in CONFLICT_STATUSES and status not in POSITIVE_STATUSES
        for status in required_statuses
    )

    if has_conflict:
        overall = 0
        grade = "blocked"
    else:
        if optional_score is None:
            overall = required_score or 0
        else:
            overall = round((required_score or 0) * 0.8 + optional_score * 0.2)
        if has_unresolved:
            overall = min(overall, 49)
            grade = "unresolved"
        elif overall >= 85:
            grade = "strong"
        elif overall >= 70:
            grade = "good"
        elif overall >= 50:
            grade = "tentative"
        else:
            grade = "weak"

    return {
        "bundle_score": overall,
        "bundle_grade": grade,
        "required_score": required_score,
        "optional_score": optional_score,
        "optional_resources": list(optional),
    }


def classify_identity_bundle(availability, required_resources):
    """Classify one candidate without pretending `not_found` is claimable.

    `conflict` means at least one MUST-HAVE resource is definitively blocked.
    `confirmed` means every MUST-HAVE resource is directly actionable.
    `promising` means every MUST-HAVE resource is non-conflicting but at least
    one is only `not_found`, so final claimability is still unconfirmed.
    `unresolved` covers missing, rate-limited, unknown, or legacy results.
    """
    required = normalize_resources(required_resources)
    rows = availability if isinstance(availability, dict) else {}
    statuses = {}
    for resource in required:
        statuses[resource] = _normalized_status(rows.get(resource))

    conflicts = [
        resource for resource, status in statuses.items()
        if status in CONFLICT_STATUSES
    ]
    unresolved = [
        resource for resource, status in statuses.items()
        if status not in CONFLICT_STATUSES and status not in POSITIVE_STATUSES
    ]
    confirmed = [
        resource for resource, status in statuses.items()
        if status in CONFIRMED_STATUSES
    ]
    promising = [
        resource for resource, status in statuses.items()
        if status in PROMISING_STATUSES
    ]

    if conflicts:
        state = "conflict"
    elif unresolved:
        state = "unresolved"
    elif len(confirmed) == len(required):
        state = "confirmed"
    else:
        state = "promising"

    result = {
        "bundle_state": state,
        "required_resources": list(required),
        "bundle_conflicts": conflicts,
        "bundle_unresolved": unresolved,
        "bundle_confirmed": confirmed,
        "bundle_promising": promising,
        "bundle_statuses": statuses,
    }
    result.update(score_identity_bundle(rows, required))
    return result
