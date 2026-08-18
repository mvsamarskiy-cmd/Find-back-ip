"""Conservative live promotion for benchmarked Socialscan evidence.

X keeps the existing behavior. Instagram is positive-only: Socialscan may
strengthen exact occupied/invalid evidence, but availability/absence responses
never override the legacy Instagram result and never become claimable.
"""

import os

import availability
from verification.providers import socialscan_adapter


def _from_evidence(name, evidence, platform):
    handle = str(name).strip().lower()
    platform = str(platform).strip().lower()
    url = {
        "x": f"https://x.com/{handle}",
        "instagram": f"https://www.instagram.com/{handle}/",
    }[platform]
    label = "X" if platform == "x" else "Instagram"
    signal = str((evidence or {}).get("signal") or "unknown")
    confidence = float((evidence or {}).get("confidence") or 0.0)
    detail = str((evidence or {}).get("detail") or "")[:300]

    if signal == "exists":
        return availability._result(
            "taken",
            detail or f"Socialscan registration probe reports this {label} username is occupied",
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
            detail or f"Socialscan reports this {label} username is invalid",
            url,
            source="socialscan",
            method="registration_probe",
            confidence=min(confidence or 0.88, 0.88),
            occupancy="unknown",
            claimability="not_claimable",
        )
    if signal == "claimable" and platform == "x":
        # Deliberately *not* `claimable`: free-handle precision has not been
        # benchmarked and Socialscan uses undocumented registration paths.
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
    promoted = _from_evidence(name, evidence, "x")
    if promoted is None:
        return legacy_row
    if isinstance(legacy_row, dict) and legacy_row.get("status") == "taken":
        return legacy_row
    return promoted


def enrich_instagram(name, legacy_row):
    """Use Socialscan only as positive Instagram occupancy evidence.

    The provider has been inconsistent across live runs for Instagram. Therefore
    `exists`/`invalid` can strengthen the result, while claimable/absent/unknown
    evidence leaves the existing Instagram checker untouched.
    """
    evidence = socialscan_adapter.check_username(name, "instagram")
    promoted = _from_evidence(name, evidence, "instagram")
    if promoted is None:
        return legacy_row
    if isinstance(legacy_row, dict) and legacy_row.get("status") == "taken":
        return legacy_row
    return promoted


__all__ = ["enrich_x", "enrich_instagram"]
