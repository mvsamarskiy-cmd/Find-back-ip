"""Collect independent live provider evidence once, then reuse it everywhere.

This is the migration layer between legacy availability rows and the central
Verification v2 collector. Provider adapters are called at most once per
platform for one `check_all` pass. Their raw evidence is preserved, while unsafe
negative/ambiguous signals are tagged as non-blocking so they remain observable
without changing availability semantics.
"""

import os

import availability
from verification.fusion import SOURCE_AUTHORITY
from verification.providers import (
    fragment_username_adapter,
    meta_instagram_oembed_adapter,
    socialscan_adapter,
    tiktok_oembed_adapter,
    whatsmyname_adapter,
)


DECISIVE_LEGACY_STATUSES = frozenset({
    "taken",
    "reserved",
    "invalid",
    "claimable",
    "purchasable",
})


def _metadata(row):
    value = row.get("metadata") if isinstance(row, dict) else None
    return dict(value) if isinstance(value, dict) else {}


def _tag(row, *, signal=None, non_blocking=False, confidence_cap=None, raw_signal=None):
    if not isinstance(row, dict):
        return None
    result = dict(row)
    original_signal = str(result.get("signal") or "unknown")
    if signal is not None:
        result["signal"] = signal
    if confidence_cap is not None:
        try:
            result["confidence"] = min(float(result.get("confidence") or 0.0), float(confidence_cap))
        except (TypeError, ValueError):
            result["confidence"] = 0.0
    metadata = _metadata(result)
    if raw_signal is not None or signal != original_signal:
        metadata["raw_signal"] = raw_signal or original_signal
    if non_blocking:
        metadata["non_blocking"] = True
    result["metadata"] = metadata
    return result


def _normalize_socialscan(row):
    signal = str((row or {}).get("signal") or "unknown")
    if signal == "claimable":
        # We have benchmarked Socialscan for occupied X handles, not free-handle
        # precision. Keep its availability response as absence-only evidence.
        return _tag(row, signal="absent", confidence_cap=0.78, raw_signal="claimable")
    if signal in {"exists", "invalid"}:
        return _tag(row)
    return _tag(row, non_blocking=True)


def _normalize_positive_only(row):
    signal = str((row or {}).get("signal") or "unknown")
    if signal in {"exists", "invalid"}:
        return _tag(row)
    return _tag(row, non_blocking=True)


def _normalize_fragment(row):
    signal = str((row or {}).get("signal") or "unknown")
    if signal == "purchasable":
        # Fragment marketplace availability is not a free Telegram claim. For
        # NameMachine it is a paid/reserved conflict, never AVAILABLE_VERIFIED.
        return _tag(row, signal="reserved", raw_signal="purchasable")
    if signal in {"exists", "reserved", "invalid"}:
        return _tag(row)
    return _tag(row, non_blocking=True)


def _normalize_whatsmyname(row):
    signal = str((row or {}).get("signal") or "unknown")
    if signal == "exists":
        return _tag(row)
    # Missing fingerprints have produced false negatives in the live benchmark.
    # Preserve them for diagnostics, but never let them drive a verdict.
    return _tag(row, non_blocking=True)


def _needs_secondary(row):
    return not (isinstance(row, dict) and row.get("status") in DECISIVE_LEGACY_STATUSES)


def collect_live_provider_evidence(handle, legacy_availability):
    """Return independent provider evidence keyed by platform.

    Only currently production-approved provider paths are called. Strong legacy
    terminal states skip secondary calls for latency. Telegram unresolved states
    collect both Fragment and WhatsMyName so one provider can no longer hide the
    other's evidence through early return.
    """
    rows = legacy_availability if isinstance(legacy_availability, dict) else {}
    result = {}

    x_row = rows.get("x")
    if "x" in rows and _needs_secondary(x_row) and not os.environ.get("X_BEARER_TOKEN", "").strip():
        evidence = _normalize_socialscan(socialscan_adapter.check_username(handle, "x"))
        if evidence:
            result["x"] = [evidence]

    instagram_row = rows.get("instagram")
    if "instagram" in rows and _needs_secondary(instagram_row):
        evidence = _normalize_positive_only(
            meta_instagram_oembed_adapter.check_username(handle, "instagram")
        )
        if evidence:
            result["instagram"] = [evidence]

    tiktok_row = rows.get("tiktok")
    if "tiktok" in rows and _needs_secondary(tiktok_row):
        evidence = _normalize_positive_only(
            tiktok_oembed_adapter.check_username(handle, "tiktok")
        )
        if evidence:
            result["tiktok"] = [evidence]

    telegram_row = rows.get("telegram")
    if "telegram" in rows and _needs_secondary(telegram_row):
        fragment = _normalize_fragment(
            fragment_username_adapter.check_username(handle, "telegram")
        )
        wmn = _normalize_whatsmyname(
            whatsmyname_adapter.check_username(handle, "telegram")
        )
        result["telegram"] = [row for row in (fragment, wmn) if row]

    return result


def _is_non_blocking(row):
    return bool(_metadata(row).get("non_blocking"))


def _confidence(row):
    try:
        return max(0.0, min(1.0, float(row.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _authority(row):
    return int(SOURCE_AUTHORITY.get(str(row.get("source") or ""), 10))


def _best(rows):
    return max(rows, key=lambda row: (_authority(row), _confidence(row)))


def _legacy_result_from_evidence(handle, row):
    signal = str(row.get("signal") or "unknown")
    status_map = {
        "exists": "taken",
        "reserved": "reserved",
        "invalid": "invalid",
        "absent": "not_found",
    }
    status = status_map.get(signal)
    if status is None:
        return None

    occupancy = {
        "exists": "occupied",
        "absent": "not_found",
        "reserved": "unknown",
        "invalid": "unknown",
    }[signal]
    claimability = "unconfirmed" if signal == "absent" else "not_claimable"
    return availability._result(
        status,
        str(row.get("detail") or "")[:300],
        str(row.get("url") or ""),
        source=str(row.get("source") or "verification_v2"),
        method=str(row.get("method") or "provider_evidence"),
        confidence=_confidence(row),
        occupancy=occupancy,
        claimability=claimability,
    )


def apply_compatibility_evidence(handle, platform, legacy_row, provider_evidence):
    """Project independent evidence back into the legacy compatibility payload.

    Verification v2 remains authoritative for the final verdict. This projection
    only preserves current UI/count behavior while the frontend migrates to the
    richer evidence model.
    """
    if not _needs_secondary(legacy_row):
        return legacy_row

    rows = [row for row in (provider_evidence or ()) if isinstance(row, dict) and not _is_non_blocking(row)]
    if not rows:
        return legacy_row

    invalid = [row for row in rows if row.get("signal") == "invalid"]
    if invalid:
        return _legacy_result_from_evidence(handle, _best(invalid)) or legacy_row

    occupied = [row for row in rows if row.get("signal") in {"exists", "reserved"}]
    if occupied:
        return _legacy_result_from_evidence(handle, _best(occupied)) or legacy_row

    absent = [row for row in rows if row.get("signal") == "absent"]
    if absent:
        return _legacy_result_from_evidence(handle, _best(absent)) or legacy_row

    return legacy_row


__all__ = [
    "apply_compatibility_evidence",
    "collect_live_provider_evidence",
]
