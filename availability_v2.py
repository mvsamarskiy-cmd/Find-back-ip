"""Compatibility wrapper that adds Verification Engine v2 verdicts.

The legacy availability module remains the source of network checks during the
migration. This wrapper is additive: callers keep receiving every legacy field,
plus a ``verification`` map with deterministic v2 verdicts.
"""

from functools import partial
from concurrent.futures import ThreadPoolExecutor
import os

import availability as legacy
from verification.bridge import attach_verification_verdicts
from verification.instagram_live import enrich_instagram
from verification.socialscan_live import enrich_x
from verification.telegram_live import enrich_telegram
from verification.tiktok_live import enrich_tiktok


RESOURCE_KEYS = legacy.RESOURCE_KEYS
normalize_resources = legacy.normalize_resources


def _recount(result):
    availability = result.get("availability") or {}
    statuses = [row.get("status", "unknown") for row in availability.values() if isinstance(row, dict)]
    status_counts = {status: statuses.count(status) for status in legacy.STATUS_VALUES}
    total = len(availability)
    claimable_count = status_counts["claimable"]
    purchasable_count = status_counts["purchasable"]
    actionable_count = sum(status_counts[status] for status in legacy.ACTIONABLE_STATUSES)
    unresolved_count = sum(status_counts[status] for status in legacy.UNRESOLVED_STATUSES)

    result.update({
        "status_counts": status_counts,
        "claimable_count": claimable_count,
        "purchasable_count": purchasable_count,
        "actionable_count": actionable_count,
        "not_found_count": status_counts["not_found"],
        "taken_count": status_counts["taken"],
        "invalid_count": status_counts["invalid"],
        "reserved_count": status_counts["reserved"],
        "rate_limited_count": status_counts["rate_limited"],
        "unknown_count": status_counts["unknown"],
        "unresolved_count": unresolved_count,
        "total_resources": total,
        "all_claimable": claimable_count == total,
        "all_verified": unresolved_count == 0,
        "available_count": actionable_count,
        "all_available": actionable_count == total,
    })
    return result


def _augment(handle, payload):
    result = dict(payload or {})
    availability = dict(result.get("availability") or {})
    changed = False
    if "x" in availability:
        availability["x"] = enrich_x(handle, availability.get("x"))
        changed = True
    if "instagram" in availability:
        availability["instagram"] = enrich_instagram(handle, availability.get("instagram"))
        changed = True
    if "tiktok" in availability:
        availability["tiktok"] = enrich_tiktok(handle, availability.get("tiktok"))
        changed = True
    if "telegram" in availability:
        availability["telegram"] = enrich_telegram(handle, availability.get("telegram"))
        changed = True
    if changed:
        result["availability"] = availability
        _recount(result)
    result["verification"] = attach_verification_verdicts(handle, availability)
    return result


def check_all(name, resources=None):
    """Run legacy checks, enrich benchmarked no-key evidence, and attach v2 verdicts."""
    return _augment(name, legacy.check_all(name, resources=resources))


def check_many(names, max_workers=None, resources=None):
    """Check several names concurrently and return additive v2 payloads.

    We intentionally call this module's ``check_all`` instead of delegating to
    legacy.check_many so every result is augmented consistently.
    """
    names = list(names)
    if not names:
        return []
    selected_resources = normalize_resources(resources)
    workers = max_workers or int(os.environ.get("AVAILABILITY_WORKERS", "8"))
    workers = max(1, min(workers, 12, len(names)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        checker = partial(check_all, resources=selected_resources)
        return list(executor.map(checker, names))
