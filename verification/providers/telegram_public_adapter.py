"""No-key Telegram occupancy probe using Telegram's public t.me pages.

Telegram documents t.me/<username> as the public username-link format. This
adapter is deliberately positive-only: it promotes only profile/channel page
structures that indicate a real peer. Generic contact shells, missing pages,
rate limits, and ambiguous responses remain UNKNOWN and never imply
claimability.
"""
from time import perf_counter

import requests

from verification.models import Evidence

TIMEOUT = 6


def _evidence(handle, signal, detail, *, confidence=0.0, latency_ms=None, http_status=None, method="public_username_page"):
    return Evidence(
        platform="telegram",
        handle=handle,
        source="telegram_public_web",
        method=method,
        signal=signal,
        confidence=confidence,
        detail=detail,
        url=f"https://t.me/{handle}",
        latency_ms=latency_ms,
        http_status=http_status,
        metadata={
            "no_api_key": True,
            "official_t_me": True,
            "positive_only": True,
            "authoritative_claimability": False,
        },
    ).to_dict()


def check_username(handle, platform="telegram"):
    handle = str(handle).strip().lower().lstrip("@")
    platform = str(platform).strip().lower()
    if platform != "telegram":
        return _evidence(handle, "unknown", "Telegram public probe supports Telegram only")

    # Telegram documents basic usernames as 5-32 chars using letters, digits
    # and underscores. Invalid local syntax is useful evidence, but it is not
    # an availability claim.
    if not (5 <= len(handle) <= 32) or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in handle):
        return _evidence(handle, "invalid", "Username does not match Telegram's documented basic username syntax", confidence=0.99)

    url = f"https://t.me/{handle}"
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
        return _evidence(handle, "unknown", f"Telegram public-page error: {type(error).__name__}", latency_ms=latency)

    latency = int((perf_counter() - started) * 1000)
    status = response.status_code
    if status == 429:
        return _evidence(handle, "rate_limited", "Telegram rate limited the public-page probe", latency_ms=latency, http_status=status)
    if status in (401, 403):
        return _evidence(handle, "unknown", f"Telegram blocked the public-page probe ({status})", latency_ms=latency, http_status=status)
    if status == 404:
        return _evidence(handle, "unknown", "Telegram returned 404; claimability is not proven", latency_ms=latency, http_status=status)
    if status != 200:
        return _evidence(handle, "unknown", f"Telegram public page HTTP {status}", latency_ms=latency, http_status=status)

    text = response.text.lower()

    # Real Telegram peers expose the profile/channel card. A bare contact shell
    # is intentionally not enough because t.me may render generic pages for
    # unresolved usernames.
    structural_markers = (
        'class="tgme_page_title"',
        'class="tgme_page_extra"',
    )
    has_profile_card = all(marker in text for marker in structural_markers)
    has_peer_action = any(marker in text for marker in (
        'class="tgme_action_button_new"',
        'class="tgme_page_action"',
        'tgme_page_context_link',
    ))
    generic_missing = any(marker in text for marker in (
        "if you have telegram, you can contact @",
        "username not found",
        "this username doesn't exist",
        "this username doesn’t exist",
    ))

    if has_profile_card and has_peer_action and not generic_missing:
        return _evidence(
            handle,
            "exists",
            "Telegram public page contains a concrete peer profile/channel card",
            confidence=0.9,
            latency_ms=latency,
            http_status=status,
        )

    return _evidence(
        handle,
        "unknown",
        "Telegram public page was reachable but concrete peer identity was not proven",
        latency_ms=latency,
        http_status=status,
    )
