from .fusion import fuse_evidence
from .models import Evidence


STATUS_TO_SIGNAL = {
    "claimable": "claimable",
    "purchasable": "purchasable",
    "taken": "exists",
    "not_found": "absent",
    "invalid": "invalid",
    "reserved": "reserved",
    "rate_limited": "rate_limited",
    "unknown": "unknown",
}


def legacy_result_to_evidence(platform, handle, result):
    """Convert one current availability.py result into Verification v2 evidence.

    This adapter is deliberately lossless for the fields that matter to the
    verifier and does not reinterpret `not_found` as claimable.
    """
    row = result if isinstance(result, dict) else {}
    status = str(row.get("status", "unknown"))
    signal = STATUS_TO_SIGNAL.get(status, "unknown")
    metadata = {}
    for key in ("occupancy", "claimability", "offer"):
        if key in row:
            metadata[key] = row[key]

    return Evidence(
        platform=str(platform),
        handle=str(handle).lower(),
        source=str(row.get("source", "legacy_availability")),
        method=str(row.get("method", "legacy_result")),
        signal=signal,
        confidence=row.get("confidence", 0.0),
        detail=str(row.get("detail", "")),
        url=str(row.get("url", "")),
        checked_at=str(row.get("checked_at", "")) or Evidence.__dataclass_fields__["checked_at"].default_factory(),
        http_status=row.get("http_status"),
        latency_ms=row.get("latency_ms"),
        metadata=metadata,
    )


def verdict_from_legacy_result(platform, handle, result):
    evidence = legacy_result_to_evidence(platform, handle, result)
    return fuse_evidence(platform, handle, [evidence.to_dict()]).to_dict()


def attach_verification_verdicts(handle, availability):
    """Return an additive v2 verdict map for the current availability payload."""
    rows = availability if isinstance(availability, dict) else {}
    return {
        platform: verdict_from_legacy_result(platform, handle, result)
        for platform, result in rows.items()
    }
