"""Positive-only Instagram enrichment using Meta's tokenless oEmbed endpoint.

Only exact positive existence evidence is promoted. Negative, unavailable,
rate-limited, malformed, or otherwise inconclusive oEmbed responses preserve the
legacy Instagram result and can never imply claimability.
"""
import availability
from verification.providers import meta_instagram_oembed_adapter


def enrich_instagram(name, legacy_row):
    if isinstance(legacy_row, dict) and legacy_row.get("status") == "taken":
        return legacy_row

    evidence = meta_instagram_oembed_adapter.check_username(name, "instagram")
    if not isinstance(evidence, dict) or evidence.get("signal") != "exists":
        return legacy_row

    handle = str(name).strip().lower()
    confidence = float(evidence.get("confidence") or 0.0)
    detail = str(evidence.get("detail") or "")[:300]
    return availability._result(
        "taken",
        detail or "Meta tokenless Instagram oEmbed returned the exact profile",
        f"https://www.instagram.com/{handle}/",
        source="meta_instagram_oembed",
        method="tokenless_oembed_profile",
        confidence=min(confidence or 0.95, 0.95),
        occupancy="occupied",
        claimability="not_claimable",
    )


__all__ = ["enrich_instagram"]
