from .models import VerificationVerdict


AUTHORITATIVE_SOURCES = frozenset({
    "namecom_core_api",
    "youtube_data_api",
    "x_api",
    "verisign_rdap",
})


def _confidence(row):
    try:
        return max(0.0, min(1.0, float(row.get("confidence", 0.0))))
    except (TypeError, ValueError):
        return 0.0


def fuse_evidence(platform, handle, evidence):
    """Fuse evidence deterministically without letting weak absence beat proof.

    The first version is intentionally conservative. A positive claimability
    verdict requires an explicit claimable/purchasable signal. Absence-only
    evidence can produce LIKELY_AVAILABLE, never AVAILABLE_VERIFIED.
    """
    rows = [dict(row) for row in evidence if isinstance(row, dict)]

    claimable = [row for row in rows if row.get("signal") in {"claimable", "purchasable"}]
    if claimable:
        best = max(claimable, key=_confidence)
        return VerificationVerdict(
            platform=platform,
            handle=handle,
            verdict="available_verified",
            confidence=_confidence(best),
            evidence=rows,
            reason="A provider explicitly confirmed a claimable or purchasable path.",
        )

    conflicts = [row for row in rows if row.get("signal") in {"exists", "reserved", "invalid"}]
    if conflicts:
        best = max(conflicts, key=_confidence)
        signal = best.get("signal")
        verdict = "taken" if signal == "exists" else signal
        return VerificationVerdict(
            platform=platform,
            handle=handle,
            verdict=verdict,
            confidence=_confidence(best),
            evidence=rows,
            reason="A provider returned direct conflict evidence.",
        )

    absent = [row for row in rows if row.get("signal") == "absent"]
    if absent:
        strongest = max(_confidence(row) for row in absent)
        independent_sources = {str(row.get("source", "")) for row in absent if row.get("source")}
        corroboration_bonus = min(0.08, max(0, len(independent_sources) - 1) * 0.04)
        confidence = min(0.95, strongest + corroboration_bonus)
        return VerificationVerdict(
            platform=platform,
            handle=handle,
            verdict="likely_available",
            confidence=confidence,
            evidence=rows,
            reason="No public account was observed, but claimability was not directly confirmed.",
        )

    return VerificationVerdict(
        platform=platform,
        handle=handle,
        verdict="unknown",
        confidence=0.0,
        evidence=rows,
        reason="No decisive verification evidence is available.",
    )
