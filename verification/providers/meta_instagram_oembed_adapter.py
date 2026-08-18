"""Benchmark-only tokenless Instagram existence probe using Meta oEmbed.

Meta's official WordPress plugin registers the tokenless Instagram oEmbed
endpoint for profile URLs. This adapter treats only a successful response that
clearly refers to the requested Instagram profile as positive existence
evidence. All negative/error outcomes fail closed and never imply claimability.
"""
from time import perf_counter

import requests

from verification.models import Evidence


OEMBED_URL = "https://graph.facebook.com/v25.0/instagram_oembed"
TIMEOUT = 6


def _evidence(handle, signal, detail, *, confidence=0.0, latency_ms=None, http_status=None):
    return Evidence(
        platform="instagram",
        handle=handle,
        source="meta_instagram_oembed",
        method="tokenless_oembed_profile",
        signal=signal,
        confidence=confidence,
        detail=detail,
        url=f"https://www.instagram.com/{handle}/",
        latency_ms=latency_ms,
        http_status=http_status,
        metadata={
            "no_api_key": True,
            "official_meta_endpoint": True,
            "authoritative_claimability": False,
        },
    ).to_dict()


def check_username(handle, platform="instagram"):
    handle = str(handle).strip().lower()
    platform = str(platform).strip().lower()
    if platform != "instagram":
        return _evidence(handle, "unknown", "Meta Instagram oEmbed probe supports Instagram only")

    profile_url = f"https://www.instagram.com/{handle}/"
    started = perf_counter()
    try:
        response = requests.get(
            OEMBED_URL,
            params={"url": profile_url, "format": "json"},
            timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NameMachine/6.5)"},
        )
    except requests.RequestException as error:
        latency = int((perf_counter() - started) * 1000)
        return _evidence(handle, "unknown", f"Meta Instagram oEmbed error: {type(error).__name__}", latency_ms=latency)

    latency = int((perf_counter() - started) * 1000)
    status = response.status_code
    if status == 200:
        try:
            payload = response.json()
        except (TypeError, ValueError):
            return _evidence(handle, "unknown", "Meta Instagram oEmbed returned non-JSON response", latency_ms=latency, http_status=status)

        text_parts = []
        if isinstance(payload, dict):
            for key in ("html", "title", "author_name", "provider_name"):
                value = payload.get(key)
                if isinstance(value, str):
                    text_parts.append(value.lower())
        joined = " ".join(text_parts)
        exact_markers = (
            f"instagram.com/{handle}",
            f"instagram.com/{handle}/",
            f"@{handle}",
        )
        if any(marker in joined for marker in exact_markers):
            return _evidence(
                handle,
                "exists",
                "Meta tokenless Instagram oEmbed returned the exact profile",
                confidence=0.95,
                latency_ms=latency,
                http_status=status,
            )
        return _evidence(
            handle,
            "unknown",
            "Meta Instagram oEmbed succeeded but exact profile identity was not proven",
            confidence=0.0,
            latency_ms=latency,
            http_status=status,
        )

    if status == 429:
        return _evidence(handle, "rate_limited", "Meta Instagram oEmbed rate limited the probe", latency_ms=latency, http_status=status)
    # A non-200 oEmbed response can mean private/unsupported/deleted/blocked or
    # other policy state, so it is not safe even as absence evidence.
    return _evidence(handle, "unknown", f"Meta Instagram oEmbed HTTP {status}", latency_ms=latency, http_status=status)
