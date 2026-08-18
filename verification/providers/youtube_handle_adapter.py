"""No-key YouTube handle existence probe using the public handle URL.

YouTube documents handle URLs as unique channel URLs in the form
``youtube.com/@handle``. This adapter treats only an exact handle marker in a
successful public page as positive occupancy evidence. Missing, blocked,
redirected, or otherwise ambiguous responses fail closed and never imply
claimability.
"""
from time import perf_counter

import requests

from verification.models import Evidence

TIMEOUT = 6


def _evidence(handle, signal, detail, *, confidence=0.0, latency_ms=None, http_status=None):
    return Evidence(
        platform="youtube",
        handle=handle,
        source="youtube_public_handle",
        method="public_handle_exact",
        signal=signal,
        confidence=confidence,
        detail=detail,
        url=f"https://www.youtube.com/@{handle}",
        latency_ms=latency_ms,
        http_status=http_status,
        metadata={
            "no_api_key": True,
            "official_handle_url": True,
            "authoritative_claimability": False,
        },
    ).to_dict()


def check_username(handle, platform="youtube"):
    handle = str(handle).strip().lower()
    platform = str(platform).strip().lower()
    if platform != "youtube":
        return _evidence(handle, "unknown", "YouTube public-handle probe supports YouTube only")

    url = f"https://www.youtube.com/@{handle}"
    started = perf_counter()
    try:
        response = requests.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; NameMachine/6.7)",
                "Accept-Language": "en-US,en;q=0.8",
            },
        )
    except requests.RequestException as error:
        latency = int((perf_counter() - started) * 1000)
        return _evidence(handle, "unknown", f"YouTube public handle error: {type(error).__name__}", latency_ms=latency)

    latency = int((perf_counter() - started) * 1000)
    status = response.status_code
    if status == 429:
        return _evidence(handle, "rate_limited", "YouTube rate limited the public handle probe", latency_ms=latency, http_status=status)
    if status in (401, 403):
        return _evidence(handle, "unknown", f"YouTube blocked the public handle probe ({status})", latency_ms=latency, http_status=status)
    if status == 404:
        return _evidence(handle, "unknown", "YouTube returned 404; claimability is not proven", latency_ms=latency, http_status=status)
    if status != 200:
        return _evidence(handle, "unknown", f"YouTube public handle HTTP {status}", latency_ms=latency, http_status=status)

    text = response.text.lower()
    exact_markers = (
        f'"canonicalbaseurl":"/@{handle}"',
        f'"vanitychannelurl":"http://www.youtube.com/@{handle}"',
        f'"vanitychannelurl":"https://www.youtube.com/@{handle}"',
        f'youtube.com/@{handle}',
    )
    if any(marker in text for marker in exact_markers):
        return _evidence(
            handle,
            "exists",
            "YouTube public page contains the exact documented handle URL",
            confidence=0.9,
            latency_ms=latency,
            http_status=status,
        )
    return _evidence(
        handle,
        "unknown",
        "YouTube public handle page was successful but exact identity was not proven",
        latency_ms=latency,
        http_status=status,
    )
