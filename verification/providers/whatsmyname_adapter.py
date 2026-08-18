"""No-key adapter for the WhatsMyName community fingerprint dataset.

This provider is evidence-only. It can corroborate public account existence or
absence, but it must never be treated as authoritative claimability.
"""
from functools import lru_cache
from time import perf_counter

import requests

from verification.models import Evidence


DATA_URL = "https://raw.githubusercontent.com/WebBreacher/WhatsMyName/main/wmn-data.json"
TIMEOUT = 6
PLATFORM_ALIASES = {
    "instagram": {"instagram"},
    "telegram": {"telegram"},
    "tiktok": {"tiktok"},
    "youtube": {"youtube"},
    "facebook": {"facebook"},
    "x": {"twitter", "x", "x.com"},
}


def _unknown(platform, handle, detail, latency_ms=None):
    return Evidence(
        platform=platform,
        handle=handle,
        source="whatsmyname",
        method="community_fingerprint",
        signal="unknown",
        confidence=0.0,
        detail=detail,
        latency_ms=latency_ms,
        metadata={"no_api_key": True},
    ).to_dict()


@lru_cache(maxsize=1)
def load_dataset():
    response = requests.get(DATA_URL, timeout=TIMEOUT, headers={"User-Agent": "NameMachine/verification"})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("sites"), list):
        raise ValueError("Invalid WhatsMyName dataset")
    return payload


def _find_site(platform, dataset):
    aliases = PLATFORM_ALIASES.get(platform, set())
    candidates = []
    for row in dataset.get("sites", []):
        if not isinstance(row, dict) or row.get("valid") is False:
            continue
        name = str(row.get("name", "")).strip().lower()
        if name in aliases:
            candidates.append(row)
    return candidates[0] if candidates else None


def _render(value, handle):
    return str(value or "").replace("{account}", handle)


def check_username(handle, platform, *, dataset=None, requester=requests.request):
    handle = str(handle).strip().lower()
    platform = str(platform).strip().lower()
    if platform not in PLATFORM_ALIASES:
        return _unknown(platform, handle, "WhatsMyName platform mapping is unavailable")

    started = perf_counter()
    try:
        data = dataset or load_dataset()
        site = _find_site(platform, data)
        if site is None:
            return _unknown(platform, handle, "WhatsMyName has no active fingerprint for this resource")

        clean_handle = handle
        for char in str(site.get("strip_bad_char", "")):
            clean_handle = clean_handle.replace(char, "")

        headers = dict(site.get("headers") or {})
        headers.setdefault("User-Agent", "Mozilla/5.0 (compatible; NameMachine/verification)")
        post_body = site.get("post_body")
        method = "POST" if isinstance(post_body, str) and post_body else "GET"
        kwargs = {
            "timeout": TIMEOUT,
            "headers": headers,
            "allow_redirects": False,
        }
        if method == "POST":
            kwargs["data"] = _render(post_body, clean_handle)
        response = requester(method, _render(site.get("uri_check"), clean_handle), **kwargs)
        text = str(getattr(response, "text", ""))
        code = int(getattr(response, "status_code", 0) or 0)
    except Exception as error:
        latency = int((perf_counter() - started) * 1000)
        return _unknown(platform, handle, f"WhatsMyName failed: {type(error).__name__}", latency)

    latency = int((perf_counter() - started) * 1000)
    exists_code = site.get("e_code")
    missing_code = site.get("m_code")
    exists_string = str(site.get("e_string", ""))
    missing_string = str(site.get("m_string", ""))

    exists_match = code == exists_code and (not exists_string or exists_string in text)
    missing_match = code == missing_code and (not missing_string or missing_string in text)

    if exists_match and not missing_match:
        signal, confidence, detail = "exists", 0.84, "WhatsMyName fingerprint matched an existing account"
    elif missing_match and not exists_match:
        signal, confidence, detail = "absent", 0.68, "WhatsMyName fingerprint matched a missing public account"
    else:
        signal, confidence, detail = "unknown", 0.0, "WhatsMyName response was inconclusive"

    return Evidence(
        platform=platform,
        handle=handle,
        source="whatsmyname",
        method="community_fingerprint",
        signal=signal,
        confidence=confidence,
        detail=detail,
        url=_render(site.get("uri_pretty") or site.get("uri_check"), clean_handle),
        latency_ms=latency,
        http_status=code or None,
        metadata={
            "no_api_key": True,
            "site": site.get("name"),
            "protection": list(site.get("protection") or []),
        },
    ).to_dict()
