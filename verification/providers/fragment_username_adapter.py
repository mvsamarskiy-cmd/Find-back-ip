"""No-key Telegram username marketplace evidence from Fragment public pages.

Fragment is useful as a second, independent signal for collectible usernames,
but its public status labels do not safely prove that a basic Telegram username
is freely claimable. Therefore this adapter never emits CLAIMABLE. It records
only positive marketplace/occupancy evidence; generic Unavailable/unknown pages
fail closed.
"""
from time import perf_counter

import requests

from verification.models import Evidence

TIMEOUT = 6
BASE_URL = "https://fragment.com/username/{}"


def _evidence(handle, signal, detail, *, confidence=0.0, latency_ms=None, http_status=None):
    return Evidence(
        platform="telegram",
        handle=handle,
        source="fragment_public_web",
        method="fragment_username_status",
        signal=signal,
        confidence=confidence,
        detail=detail,
        url=BASE_URL.format(handle),
        latency_ms=latency_ms,
        http_status=http_status,
        metadata={
            "no_api_key": True,
            "marketplace_signal": True,
            "positive_only": True,
            "authoritative_claimability": False,
        },
    ).to_dict()


def check_username(handle, platform="telegram"):
    handle = str(handle).strip().lower().lstrip("@")
    platform = str(platform).strip().lower()
    if platform != "telegram":
        return _evidence(handle, "unknown", "Fragment username probe supports Telegram only")

    if not (5 <= len(handle) <= 32) or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in handle):
        return _evidence(handle, "invalid", "Username does not match Telegram's documented basic username syntax", confidence=0.99)

    url = BASE_URL.format(handle)
    started = perf_counter()
    try:
        response = requests.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; NameMachine/6.8)",
                "Accept-Language": "en-US,en;q=0.8",
            },
        )
    except requests.RequestException as error:
        latency = int((perf_counter() - started) * 1000)
        return _evidence(handle, "unknown", f"Fragment public-page error: {type(error).__name__}", latency_ms=latency)

    latency = int((perf_counter() - started) * 1000)
    status = response.status_code
    if status == 429:
        return _evidence(handle, "rate_limited", "Fragment rate limited the username probe", latency_ms=latency, http_status=status)
    if status in (401, 403):
        return _evidence(handle, "unknown", f"Fragment blocked the username probe ({status})", latency_ms=latency, http_status=status)
    if status != 200:
        return _evidence(handle, "unknown", f"Fragment username page HTTP {status}", latency_ms=latency, http_status=status)

    text = response.text.lower()

    # Public Fragment pages use explicit status labels. We only use labels that
    # are positive evidence of an existing/reserved/marketplace username.
    if 'status-taken">taken' in text or "status-taken'>taken" in text:
        return _evidence(
            handle,
            "exists",
            "Fragment explicitly marks the Telegram username as Taken",
            confidence=0.95,
            latency_ms=latency,
            http_status=status,
        )

    if ('status-unavail">sold' in text or "status-unavail'>sold" in text or
            'status-sold">sold' in text or "status-sold'>sold" in text):
        return _evidence(
            handle,
            "reserved",
            "Fragment marks the collectible username as Sold",
            confidence=0.97,
            latency_ms=latency,
            http_status=status,
        )

    if 'status-avail">available' in text or "status-avail'>available" in text:
        # On Fragment, Available means a marketplace purchase/auction path, not
        # a free basic Telegram claim. Keep the distinction explicit.
        return _evidence(
            handle,
            "purchasable",
            "Fragment exposes the username as available through its marketplace",
            confidence=0.9,
            latency_ms=latency,
            http_status=status,
        )

    # Critically, Fragment's generic "Unavailable" label is ambiguous: it does
    # not prove the basic username is free, so it remains UNKNOWN.
    return _evidence(
        handle,
        "unknown",
        "Fragment returned no safe positive username status",
        latency_ms=latency,
        http_status=status,
    )
