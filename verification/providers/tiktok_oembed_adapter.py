"""Tokenless TikTok existence probe using the official creator-profile oEmbed API.

TikTok documents creator profile embeds through GET https://www.tiktok.com/oembed
with a profile URL. Only an exact successful creator-profile response is treated
as positive existence evidence. All non-200, malformed, or ambiguous responses
fail closed and never imply username claimability.
"""
from time import perf_counter

import requests

from verification.models import Evidence


OEMBED_URL = "https://www.tiktok.com/oembed"
TIMEOUT = 6


def _evidence(handle, signal, detail, *, confidence=0.0, latency_ms=None, http_status=None):
    return Evidence(
        platform="tiktok",
        handle=handle,
        source="tiktok_oembed",
        method="official_creator_profile_oembed",
        signal=signal,
        confidence=confidence,
        detail=detail,
        url=f"https://www.tiktok.com/@{handle}",
        latency_ms=latency_ms,
        http_status=http_status,
        metadata={
            "no_api_key": True,
            "official_tiktok_endpoint": True,
            "authoritative_claimability": False,
        },
    ).to_dict()


def check_username(handle, platform="tiktok"):
    handle = str(handle).strip().lower().lstrip("@")
    platform = str(platform).strip().lower()
    if platform != "tiktok":
        return _evidence(handle, "unknown", "TikTok oEmbed probe supports TikTok only")

    profile_url = f"https://www.tiktok.com/@{handle}"
    started = perf_counter()
    try:
        response = requests.get(
            OEMBED_URL,
            params={"url": profile_url},
            timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NameMachine/6.6)"},
        )
    except requests.RequestException as error:
        latency = int((perf_counter() - started) * 1000)
        return _evidence(handle, "unknown", f"TikTok oEmbed error: {type(error).__name__}", latency_ms=latency)

    latency = int((perf_counter() - started) * 1000)
    status = response.status_code
    if status == 200:
        try:
            payload = response.json()
        except (TypeError, ValueError):
            return _evidence(handle, "unknown", "TikTok oEmbed returned non-JSON response", latency_ms=latency, http_status=status)

        if not isinstance(payload, dict):
            return _evidence(handle, "unknown", "TikTok oEmbed returned unexpected JSON", latency_ms=latency, http_status=status)

        author_url = str(payload.get("author_url") or "").lower().rstrip("/")
        html = str(payload.get("html") or "").lower()
        expected_url = profile_url.lower().rstrip("/")
        exact_author = author_url == expected_url
        exact_html_markers = (
            f'data-unique-id="{handle}"',
            f"data-unique-id='{handle}'",
            f"tiktok.com/@{handle}",
            f">@{handle}<",
        )
        exact_html = any(marker in html for marker in exact_html_markers)
        provider_ok = str(payload.get("provider_name") or "").strip().lower() == "tiktok"

        if provider_ok and (exact_author or exact_html):
            return _evidence(
                handle,
                "exists",
                "Official TikTok creator-profile oEmbed returned the exact username",
                confidence=0.97,
                latency_ms=latency,
                http_status=status,
            )
        return _evidence(
            handle,
            "unknown",
            "TikTok oEmbed succeeded but exact profile identity was not proven",
            latency_ms=latency,
            http_status=status,
        )

    if status == 429:
        return _evidence(handle, "rate_limited", "TikTok oEmbed rate limited the probe", latency_ms=latency, http_status=status)
    # A non-200 result may reflect unsupported/private/deleted/policy state; it
    # is not safe to equate this with an available username.
    return _evidence(handle, "unknown", f"TikTok oEmbed HTTP {status}", latency_ms=latency, http_status=status)
