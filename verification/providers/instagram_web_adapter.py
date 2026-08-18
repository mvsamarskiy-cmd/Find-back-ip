"""Conservative no-key Instagram existence probe.

This adapter uses Instagram's web-profile endpoint as a best-effort public
signal. It is intentionally one-way: an exact returned username can prove an
observed account exists, while 404/empty responses are only absence evidence
and never prove the username is claimable.
"""
from time import perf_counter
from urllib.parse import quote

import requests

from verification.models import Evidence


WEB_PROFILE_URL = "https://i.instagram.com/api/v1/users/web_profile_info/?username={}"
IG_APP_ID = "936619743392459"
TIMEOUT = 6


def _evidence(handle, signal, detail, *, confidence=0.0, latency_ms=None, http_status=None):
    return Evidence(
        platform="instagram",
        handle=handle,
        source="instagram_web_profile_info",
        method="web_profile_info",
        signal=signal,
        confidence=confidence,
        detail=detail,
        url=f"https://www.instagram.com/{handle}/",
        latency_ms=latency_ms,
        http_status=http_status,
        metadata={"no_api_key": True, "authoritative_claimability": False},
    ).to_dict()


def check_username(handle, platform="instagram"):
    handle = str(handle).strip().lower()
    platform = str(platform).strip().lower()
    if platform != "instagram":
        return _evidence(handle, "unknown", "Instagram web probe supports Instagram only")

    started = perf_counter()
    url = WEB_PROFILE_URL.format(quote(handle))
    headers = {
        "Accept": "application/json",
        "X-IG-App-ID": IG_APP_ID,
        "Referer": "https://www.instagram.com/",
        "Origin": "https://www.instagram.com",
        "User-Agent": "Mozilla/5.0 (compatible; NameMachine/6.5)",
    }
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException as error:
        latency = int((perf_counter() - started) * 1000)
        return _evidence(handle, "unknown", f"Instagram web probe error: {type(error).__name__}", latency_ms=latency)

    latency = int((perf_counter() - started) * 1000)
    status = response.status_code
    if status == 200:
        try:
            payload = response.json()
        except (TypeError, ValueError):
            return _evidence(handle, "unknown", "Instagram returned non-JSON response", latency_ms=latency, http_status=status)
        user = ((payload or {}).get("data") or {}).get("user") if isinstance(payload, dict) else None
        username = str((user or {}).get("username") or "").strip().lower() if isinstance(user, dict) else ""
        if username == handle:
            return _evidence(
                handle,
                "exists",
                "Instagram web-profile endpoint returned the exact username",
                confidence=0.93,
                latency_ms=latency,
                http_status=status,
            )
        if user is None or username == "":
            return _evidence(
                handle,
                "absent",
                "Instagram web-profile endpoint returned no user; claimability is unconfirmed",
                confidence=0.68,
                latency_ms=latency,
                http_status=status,
            )
        return _evidence(handle, "unknown", "Instagram returned a different username", latency_ms=latency, http_status=status)

    if status == 404:
        return _evidence(
            handle,
            "absent",
            "Instagram web-profile endpoint returned 404; claimability is unconfirmed",
            confidence=0.68,
            latency_ms=latency,
            http_status=status,
        )
    if status == 429:
        return _evidence(handle, "rate_limited", "Instagram rate limited the web-profile probe", latency_ms=latency, http_status=status)
    if status in (400, 401, 403):
        return _evidence(handle, "unknown", f"Instagram blocked or gated the web-profile probe ({status})", latency_ms=latency, http_status=status)
    return _evidence(handle, "unknown", f"Instagram web-profile HTTP {status}", latency_ms=latency, http_status=status)
