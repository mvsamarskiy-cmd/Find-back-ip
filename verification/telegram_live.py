"""Conservative live Telegram enrichment from no-key secondary evidence.

The legacy t.me checker remains the primary Telegram probe. This module adds
only positive secondary evidence from Fragment and WhatsMyName. Negative or
ambiguous secondary results are ignored. Fragment marketplace availability is
not treated as free username availability; it is converted to a reserved/paid
conflict state for the normal free-handle search.
"""
import availability
from verification.providers import fragment_username_adapter, whatsmyname_adapter


def _promote_taken(handle, evidence, source, method, confidence):
    detail = str((evidence or {}).get("detail") or "")[:300]
    return availability._result(
        "taken",
        detail or "Independent Telegram evidence confirms username occupancy",
        f"https://t.me/{handle}",
        source=source,
        method=method,
        confidence=confidence,
        occupancy="occupied",
        claimability="not_claimable",
    )


def enrich_telegram(name, legacy_row):
    """Strengthen Telegram only from positive evidence; never from absence."""
    if isinstance(legacy_row, dict) and legacy_row.get("status") in {
        "taken", "reserved", "invalid", "claimable", "purchasable"
    }:
        return legacy_row

    handle = str(name).strip().lower().lstrip("@")

    fragment = fragment_username_adapter.check_username(handle, "telegram")
    fragment_signal = fragment.get("signal") if isinstance(fragment, dict) else None

    if fragment_signal == "exists":
        return _promote_taken(
            handle,
            fragment,
            "fragment_public_web",
            "fragment_username_status",
            min(float(fragment.get("confidence") or 0.0), 0.95),
        )

    if fragment_signal in {"reserved", "purchasable"}:
        # A Fragment sale/auction path means the username is not a normal free
        # claim. Keep it out of the green actionable bucket used by NameMachine.
        detail = str(fragment.get("detail") or "")[:300]
        return availability._result(
            "reserved",
            detail or "Telegram username is controlled through the Fragment marketplace",
            f"https://fragment.com/username/{handle}",
            source="fragment_public_web",
            method="fragment_username_status",
            confidence=min(float(fragment.get("confidence") or 0.0), 0.97),
            occupancy="unknown",
            claimability="not_claimable",
        )

    # WhatsMyName is useful only as a positive collision signal. Its Telegram
    # missing fingerprint has produced a false negative in our live benchmark,
    # so `absent` is deliberately ignored.
    wmn = whatsmyname_adapter.check_username(handle, "telegram")
    if isinstance(wmn, dict) and wmn.get("signal") == "exists":
        return _promote_taken(
            handle,
            wmn,
            "whatsmyname",
            "community_fingerprint_positive_only",
            min(float(wmn.get("confidence") or 0.0), 0.84),
        )

    return legacy_row


__all__ = ["enrich_telegram"]
