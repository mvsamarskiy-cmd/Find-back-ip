from .models import VerificationVerdict


# Authority is intentionally explicit and conservative. It is used only to
# explain/score evidence, never to upgrade absence into verified availability.
SOURCE_AUTHORITY = {
    "namecom_core_api": 100,
    "youtube_data_api": 95,
    "x_api": 95,
    "verisign_rdap": 90,
    "meta_instagram_oembed": 85,
    "tiktok_oembed": 85,
    "socialscan": 70,
    "telegram_public_web": 65,
    "fragment_public_web": 65,
    "whatsmyname": 45,
    "maigret": 25,
    "public_web": 40,
    "search_engine": 30,
}


def _confidence(row):
    try:
        return max(0.0, min(1.0, float(row.get("confidence", 0.0))))
    except (TypeError, ValueError):
        return 0.0


def _authority(row):
    return int(SOURCE_AUTHORITY.get(str(row.get("source", "")), 10))


def _best(rows):
    return max(rows, key=lambda row: (_authority(row), _confidence(row)))


def _is_non_blocking(row):
    metadata = row.get("metadata") if isinstance(row, dict) else None
    return bool(isinstance(metadata, dict) and metadata.get("non_blocking"))


def _verdict(platform, handle, verdict, confidence, rows, reason):
    return VerificationVerdict(
        platform=platform,
        handle=handle,
        verdict=verdict,
        confidence=max(0.0, min(1.0, float(confidence))),
        evidence=rows,
        reason=reason,
    )


def fuse_evidence(platform, handle, evidence):
    """Fuse heterogeneous evidence with fail-closed contradiction semantics.

    Safety invariants:
    - absence alone can never become AVAILABLE_VERIFIED;
    - claimability plus occupancy conflict can never become AVAILABLE_VERIFIED;
    - INVALID input wins immediately;
    - contradictory positive evidence becomes UNKNOWN for re-check/manual review;
    - weak negative evidence never beats direct positive occupancy evidence;
    - evidence tagged ``metadata.non_blocking`` remains visible in the returned
      evidence trail but cannot change the verdict.
    """
    rows = [dict(row) for row in evidence if isinstance(row, dict)]
    decision_rows = [row for row in rows if not _is_non_blocking(row)]
    if not decision_rows:
        return _verdict(
            platform,
            handle,
            "unknown",
            0.0,
            rows,
            "No decisive verification evidence is available.",
        )

    invalid = [row for row in decision_rows if row.get("signal") == "invalid"]
    if invalid:
        best = _best(invalid)
        return _verdict(
            platform,
            handle,
            "invalid",
            _confidence(best),
            rows,
            "At least one verifier determined that the identifier is invalid for this resource.",
        )

    claimable = [row for row in decision_rows if row.get("signal") in {"claimable", "purchasable"}]
    occupied = [row for row in decision_rows if row.get("signal") in {"exists", "reserved"}]

    # A registrar/provider saying "claimable" while another source says the same
    # identifier exists/reserved is a contradiction. Never show green in that case.
    if claimable and occupied:
        strongest_claim = _best(claimable)
        strongest_conflict = _best(occupied)
        confidence = max(_confidence(strongest_claim), _confidence(strongest_conflict))
        return _verdict(
            platform,
            handle,
            "unknown",
            confidence,
            rows,
            "Contradictory positive evidence: one provider reports claimability while another reports occupancy or reservation.",
        )

    if occupied:
        best = _best(occupied)
        signal = best.get("signal")
        verdict = "taken" if signal == "exists" else "reserved"
        return _verdict(
            platform,
            handle,
            verdict,
            _confidence(best),
            rows,
            "Direct positive conflict evidence was observed.",
        )

    if claimable:
        best = _best(claimable)
        return _verdict(
            platform,
            handle,
            "available_verified",
            _confidence(best),
            rows,
            "A provider explicitly confirmed a claimable or purchasable path and no contradictory occupancy evidence is present.",
        )

    absent = [row for row in decision_rows if row.get("signal") == "absent"]
    unresolved = [
        row
        for row in decision_rows
        if row.get("signal") in {"blocked", "rate_limited", "unknown"}
    ]

    if absent:
        strongest = max(_confidence(row) for row in absent)
        independent_sources = {str(row.get("source", "")) for row in absent if row.get("source")}
        corroboration_bonus = min(0.08, max(0, len(independent_sources) - 1) * 0.04)
        confidence = min(0.95, strongest + corroboration_bonus)

        # If the only negative evidence is accompanied by an unresolved result from
        # a stronger source, do not market the handle as likely available yet.
        if unresolved:
            strongest_absent_authority = max(_authority(row) for row in absent)
            strongest_unresolved_authority = max(_authority(row) for row in unresolved)
            if strongest_unresolved_authority > strongest_absent_authority:
                return _verdict(
                    platform,
                    handle,
                    "unknown",
                    confidence,
                    rows,
                    "A stronger verifier was unresolved, so weaker absence evidence is insufficient for a likely-available verdict.",
                )

        return _verdict(
            platform,
            handle,
            "likely_available",
            confidence,
            rows,
            "No public account was observed, but claimability was not directly confirmed.",
        )

    return _verdict(
        platform,
        handle,
        "unknown",
        0.0,
        rows,
        "No decisive verification evidence is available.",
    )
