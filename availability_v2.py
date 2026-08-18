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


RESOURCE_KEYS = legacy.RESOURCE_KEYS
normalize_resources = legacy.normalize_resources


def _augment(handle, payload):
    result = dict(payload or {})
    availability = result.get("availability")
    result["verification"] = attach_verification_verdicts(handle, availability)
    return result


def check_all(name, resources=None):
    """Run the legacy checks and attach conservative v2 verdicts."""
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
