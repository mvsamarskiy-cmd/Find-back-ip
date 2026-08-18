from availability import RESOURCE_KEYS, normalize_resources


CONFLICT_STATUSES = frozenset({"taken", "reserved", "invalid"})
CONFIRMED_STATUSES = frozenset({"claimable", "purchasable"})
PROMISING_STATUSES = frozenset({"not_found"})
POSITIVE_STATUSES = CONFIRMED_STATUSES | PROMISING_STATUSES


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
        result = rows.get(resource)
        status = str(result.get("status", "unknown")) if isinstance(result, dict) else "unknown"
        if status == "available":
            status = "unknown"
        statuses[resource] = status

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

    return {
        "bundle_state": state,
        "required_resources": list(required),
        "bundle_conflicts": conflicts,
        "bundle_unresolved": unresolved,
        "bundle_confirmed": confirmed,
        "bundle_promising": promising,
        "bundle_statuses": statuses,
    }
