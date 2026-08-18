"""Positive-only TikTok enrichment using the official creator-profile oEmbed API.

Only exact positive existence evidence is promoted. Negative, unavailable,
rate-limited, malformed, or otherwise inconclusive oEmbed responses preserve the
legacy TikTok result and can never imply username claimability.
"""
import availability
from verification.providers import tiktok_oembed_adapter


def enrich_tiktok(name, legacy_row):
    if isinstance(legacy_row, dict) and legacy_row.get("status") == "taken":
        return legacy_row

    evidence = tiktok_oembed_adapter.check_username(name, "tiktok")
    if not isinstance(evidence, dict) or evidence.get("signal") != "exists":
        return legacy_row

    handle = str(name).strip().lower().lstrip("@")
    confidence = float(evidence.get("confidence") or 0.0)
    detail = str(evidence.get("detail") or "")[:300]
    return availability._result(
        "taken",
        detail or "Official TikTok creator-profile oEmbed returned the exact username",
        f"https://www.tiktok.com/@{handle}",
        source="tiktok_oembed",
        method="official_creator_profile_oembed",
        confidence=min(confidence or 0.97, 0.97),
        occupancy="occupied",
        claimability="not_claimable",
    )


__all__ = ["enrich_tiktok"]
