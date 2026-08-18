"""Conservative live promotion for benchmarked Socialscan evidence.

Only X is promoted in this release. The first live benchmark proved occupied X
handles reliably, but did not benchmark free handles. Therefore Socialscan can
confirm TAKEN/INVALID, while an `available=True` response remains only
NOT_FOUND/claimability-unconfirmed. Instagram stays benchmark-only until it has
its own live fixtures.
"""

import os

import availability
from verification.providers import socialscan_adapter


def _from_evidence(name, evidence):
    handle = str(name).strip().lower()
    url = f"https://x.com/{handle}"
    signal = str((evidence or {}).get("signal") or "unknown")
    confidence = float((evidence or {}).get("confidence") or 0.0)
    detail = str((evidence or {}).get("detail") or "")[:300]

    if signal == "exists":
        return availability._result(
            "taken",
            detail or "Socialscan registration probe reports this X username is occupied",
            url,
            source="socialscan",
            method="registration_probe",
            confidence=min(confidence or 0.9, 0.9),
            occupancy="occupied",
            claimability="not_claimable",
        )
    if signal == "invalid":
        return availability._result(
            "invalid",
            detail or "Socialscan reports this X username is invalid",
            url,
            source="socialscan",
            method="registration_probe",
            confidence=min(confidence or 0.88, 0.88),
            occupancy="unknown",
            claimability="not_claimable",
        )
    if signal == "claimable":
        # Deliberately *not* `claimable`: free-handle precision has not been
        # benchmarked yet, and Socialscan uses undocumented registration paths.
        return availability._result(
            "not_found",
            detail or "Socialscan reports availability; claimability remains unconfirmed",
            url,
            source="socialscan",
            method="registration_probe",
            confidence=min(confidence or 0.78, 0.78),
            occupancy="not_found",
            claimability="unconfirmed",
        )
    return None


def enrich_x(name, legacy_row):
    """Return a stronger conservative X row without mutating legacy globals."""
    if os.environ.get("X_BEARER_TOKEN", "").strip():
        return legacy_row

    evidence = socialscan_adapter.check_username(name, "x")
    promoted = _from_evidence(name, evidence)
    if promoted is None:
        return legacy_row

    # Existing positive occupancy evidence is never weakened by Socialscan.
    if isinstance(legacy_row, dict) and legacy_row.get("status") == "taken":
        return legacy_row
    return promoted


__all__ = ["enrich_x"]
