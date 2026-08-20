"""Collect independent live provider evidence once, then reuse it everywhere.

This is the migration layer between legacy availability rows and the central
Verification v2 collector. Provider adapters are called at most once per
platform for one `check_all` pass. Independent secondary providers run through a
bounded shared runtime so slow hosts no longer serialize the whole candidate.
"""

import os

import availability
from verification.fusion import SOURCE_AUTHORITY
from verification.provider_runtime import ProviderTask, run_provider_checks
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
        # Keep paid marketplace inventory as PURCHASABLE, not free/claimable.
        # Strict-green code only accepts CLAIMABLE, while the UI can now expose
        # the Fragment price and purchase path explicitly.
        return _tag(row, raw_signal="purchasable")
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
    """Return independent provider evidence keyed by platform."""
    rows = legacy_availability if isinstance(legacy_availability, dict) else {}
    tasks = []

    x_row = rows.get("x")
    if "x" in rows and _needs_secondary(x_row) and not os.environ.get("X_BEARER_TOKEN", "").strip():
        tasks.append(ProviderTask(
            key="x_socialscan",
            provider="socialscan",
            handle=handle,
            platform="x",
            checker=socialscan_adapter.check_username,
        ))

    instagram_row = rows.get("instagram")
    if "instagram" in rows and _needs_secondary(instagram_row):
        tasks.append(ProviderTask(
            key="instagram_meta_oembed",
            provider="meta_instagram_oembed",
            handle=handle,
            platform="instagram",
            checker=meta_instagram_oembed_adapter.check_username,
        ))

    tiktok_row = rows.get("tiktok")
    if "tiktok" in rows and _needs_secondary(tiktok_row):
        tasks.append(ProviderTask(
            key="tiktok_oembed",
            provider="tiktok_oembed",
            handle=handle,
            platform="tiktok",
            checker=tiktok_oembed_adapter.check_username,
        ))

    telegram_row = rows.get("telegram")
    if "telegram" in rows and _needs_secondary(telegram_row):
        tasks.extend((
            ProviderTask(
                key="telegram_fragment",
                provider="fragment_public_web",
                handle=handle,
                platform="telegram",
                checker=fragment_username_adapter.check_username,
            ),
            ProviderTask(
                key="telegram_whatsmyname",
                provider="whatsmyname",
                handle=handle,
                platform="telegram",
                checker=whatsmyname_adapter.check_username,
            ),
        ))

    raw = run_provider_checks(tasks)
    result = {}

    if "x_socialscan" in raw:
        evidence = _normalize_socialscan(raw["x_socialscan"])
        if evidence:
            result["x"] = [evidence]

    if "instagram_meta_oembed" in raw:
        evidence = _normalize_positive_only(raw["instagram_meta_oembed"])
        if evidence:
            result["instagram"] = [evidence]

    if "tiktok_oembed" in raw:
        evidence = _normalize_positive_only(raw["tiktok_oembed"])
        if evidence:
            result["tiktok"] = [evidence]

    telegram_rows = []
    if "telegram_fragment" in raw:
        evidence = _normalize_fragment(raw["telegram_fragment"])
        if evidence:
            telegram_rows.append(evidence)
    if "telegram_whatsmyname" in raw:
        evidence = _normalize_whatsmyname(raw["telegram_whatsmyname"])
        if evidence:
            telegram_rows.append(evidence)
    if telegram_rows:
        result["telegram"] = telegram_rows

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


def _fragment_offer(row):
    if str(row.get("source") or "") != "fragment_public_web":
        return None
    meta = _metadata(row)
    offer = {
        "provider": "fragment",
        "marketplace_url": str(meta.get("marketplace_url") or row.get("url") or ""),
        "currency": "TON",
        "purchase_type": "marketplace",
        "marketplace_status": str(meta.get("marketplace_status") or ""),
    }
    for key in ("price_ton", "minimum_bid_ton", "current_bid_ton", "sold_price_ton"):
        if meta.get(key) is not None:
            offer[key] = meta[key]
    if meta.get("price_label"):
        offer["price_label"] = str(meta.get("price_label"))[:80]
    return offer


def _legacy_result_from_evidence(handle, row):
    signal = str(row.get("signal") or "unknown")
    status_map = {
        "exists": "taken",
        "reserved": "reserved",
        "invalid": "invalid",
        "absent": "not_found",
        "purchasable": "purchasable",
    }
    status = status_map.get(signal)
    if status is None:
        return None

    occupancy = {
        "exists": "occupied",
        "absent": "not_found",
        "reserved": "unknown",
        "invalid": "unknown",
        "purchasable": "unknown",
    }[signal]
    if signal == "absent":
        claimability = "unconfirmed"
    elif signal == "purchasable":
        claimability = "purchase_available"
    else:
        claimability = "not_claimable"
    return availability._result(
        status,
        str(row.get("detail") or "")[:300],
        str(row.get("url") or ""),
        source=str(row.get("source") or "verification_v2"),
        method=str(row.get("method") or "provider_evidence"),
        confidence=_confidence(row),
        occupancy=occupancy,
        claimability=claimability,
        offer=_fragment_offer(row),
    )


def apply_compatibility_evidence(handle, platform, legacy_row, provider_evidence):
    """Project independent evidence back into the legacy compatibility payload.

    Verification v2 remains authoritative for final truth. A Fragment marketplace
    purchase path remains PURCHASABLE (paid, non-green) and carries its public TON
    offer details into the compatibility payload.
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

    purchasable = [row for row in rows if row.get("signal") == "purchasable"]
    if purchasable:
        return _legacy_result_from_evidence(handle, _best(purchasable)) or legacy_row

    absent = [row for row in rows if row.get("signal") == "absent"]
    if absent:
        return _legacy_result_from_evidence(handle, _best(absent)) or legacy_row

    return legacy_row


__all__ = [
    "apply_compatibility_evidence",
    "collect_live_provider_evidence",
]
