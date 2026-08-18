"""Conservative no-key Facebook public-page existence probe.

Facebook routinely returns login/interstitial/generic HTML to anonymous clients,
so this adapter is positive-only. It only emits ``exists`` when the response
contains concrete Facebook profile/page identity markers. Missing pages,
interstitials, blocks, rate limits, and ambiguous 200 responses remain UNKNOWN
and never imply username claimability.
"""
from time import perf_counter
import re

import requests

from verification.models import Evidence


TIMEOUT = 6
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.8",
}
PROFILE_MARKERS = (
    '"profile_id":',
    '"profile_owner":',
    '"userID":',
    '"profileTilesFeedRoute"',
    '"pageID":',
    '"page_id":',
)
NOT_FOUND_MARKERS = (
    "this content isn't available",
    "this content isn’t available",
    "page isn't available",
    "page isn’t available",
    "content not found",
    "page not found",
    "the link you followed may have expired",
    "sorry, this page isn't available",
    "sorry, this page isn’t available",
)


def _evidence(handle, signal, detail, *, confidence=0.0, latency_ms=None, http_status=None, url=None):
    return Evidence(
        platform="facebook",
        handle=handle,
        source="facebook_public_web",
        method="public_profile_page_positive_only",
        signal=signal,
        confidence=confidence,
        detail=detail,
        url=url or f"https://www.facebook.com/{handle}",
        latency_ms=latency_ms,
        http_status=http_status,
        metadata={
            "no_api_key": True,
            "positive_only": True,
            "authoritative_claimability": False,
        },
    ).to_dict()


def _exact_handle_hint(text, handle):
    escaped = re.escape(handle)
    patterns = (
        rf'https?://(?:www\.|m\.)?facebook\.com/{escaped}(?:[/?"\\]|$)',
        rf'"vanity":"{escaped}"',
        rf'"username":"{escaped}"',
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def check_username(handle, platform="facebook", *, requester=requests.get):
    handle = str(handle).strip().lower().lstrip("@")
    platform = str(platform).strip().lower()
    if platform != "facebook":
        return _evidence(handle, "unknown", "Facebook public probe supports Facebook only")

    started = perf_counter()
    url = f"https://www.facebook.com/{handle}"
    try:
        response = requester(url, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True)
    except requests.RequestException as error:
        latency = int((perf_counter() - started) * 1000)
        return _evidence(handle, "unknown", f"Facebook public-page error: {type(error).__name__}", latency_ms=latency, url=url)

    latency = int((perf_counter() - started) * 1000)
    status = int(getattr(response, "status_code", 0) or 0)
    text = str(getattr(response, "text", ""))[:250000]
    lowered = text.lower()

    if status in {403, 429}:
        signal = "rate_limited" if status == 429 else "blocked"
        return _evidence(handle, signal, f"Facebook public page HTTP {status}", latency_ms=latency, http_status=status, url=url)

    if status != 200:
        return _evidence(handle, "unknown", f"Facebook public page HTTP {status}", latency_ms=latency, http_status=status, url=url)

    if any(marker in lowered for marker in NOT_FOUND_MARKERS):
        return _evidence(handle, "unknown", "Facebook returned a missing-content page; absence is not claimability", latency_ms=latency, http_status=status, url=url)

    concrete_identity = any(marker.lower() in lowered for marker in PROFILE_MARKERS)
    exact_handle = _exact_handle_hint(text, handle)
    if concrete_identity and exact_handle:
        return _evidence(
            handle,
            "exists",
            "Facebook public page exposed concrete profile/page identity for the exact handle",
            confidence=0.88,
            latency_ms=latency,
            http_status=status,
            url=url,
        )

    return _evidence(
        handle,
        "unknown",
        "Facebook anonymous response did not prove exact profile identity",
        latency_ms=latency,
        http_status=status,
        url=url,
    )
