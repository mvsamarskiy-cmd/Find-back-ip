"""Exact-identity gates for the Browser Eye service.

A requested profile URL is not proof that the requested username exists: social
sites often keep the requested URL while rendering an error/login shell.  This
overlay requires an exact observed identity signal and tightens Google-result URL
matching.  It never promotes absence to claimability.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit


ERROR_SHELL_MARKERS = (
    "something went wrong",
    "try again",
    "an error occurred",
    "content unavailable",
    "content is unavailable",
    "this content isn't available",
    "this content isn’t available",
    "щось пішло не так",
    "спробуйте ще раз",
    "контент недоступний",
    "сталася помилка",
)


def _safe(value, limit=200000):
    return str(value or "")[:limit]


def _observed_usernames(text):
    haystack = _safe(text, 360000)
    patterns = (
        r'"username"\s*:\s*"@?([A-Za-z0-9_.-]{2,64})"',
        r'"uniqueId"\s*:\s*"@?([A-Za-z0-9_.-]{2,64})"',
        r'"screen_name"\s*:\s*"@?([A-Za-z0-9_.-]{2,64})"',
        r'"vanity"\s*:\s*"@?([A-Za-z0-9_.-]{2,64})"',
        r'"handle"\s*:\s*"@?([A-Za-z0-9_.-]{2,64})"',
    )
    output = []
    seen = set()
    for pattern in patterns:
        for match in re.finditer(pattern, haystack, flags=re.I):
            value = match.group(1).lower()
            if value not in seen:
                seen.add(value)
                output.append(value)
            if len(output) >= 12:
                return output
    return output


def _meta_handle(text):
    values = []
    for match in re.finditer(r"(?<![A-Za-z0-9_.-])@([A-Za-z0-9_.-]{2,64})(?![A-Za-z0-9_.-])", _safe(text, 1600)):
        value = match.group(1).lower()
        if value not in values:
            values.append(value)
    return values


def _exact_profile_url(platform, handle, url):
    try:
        parsed = urlsplit(str(url or ""))
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    expected = {
        "instagram": ("instagram.com", f"/{handle}"),
        "telegram": ("t.me", f"/{handle}"),
        "tiktok": ("tiktok.com", f"/@{handle}"),
        "youtube": ("youtube.com", f"/@{handle}"),
        "facebook": ("facebook.com", f"/{handle}"),
        "x": ("x.com", f"/{handle}"),
    }.get(str(platform or "").lower())
    if not expected:
        return False
    expected_host, expected_path = expected
    return (host == expected_host or host.endswith("." + expected_host)) and path == expected_path


def install_browser_eye_hardening(service_module) -> None:
    base_profile = service_module.fingerprint_from_snapshot
    base_search = service_module.search_fingerprint
    if getattr(base_profile, "_exact_identity_gate", False):
        return

    def profile(platform, handle, snapshot, network_rows=None, *, engine="chromium", latency_ms=None, http_status=None):
        result = base_profile(
            platform,
            handle,
            snapshot,
            network_rows,
            engine=engine,
            latency_ms=latency_ms,
            http_status=http_status,
        )
        clean_handle = service_module._clean_handle(handle)
        snap = dict(snapshot or {}) if isinstance(snapshot, dict) else {}
        network_rows_list = list(network_rows or [])
        scripts = _safe(snap.get("script_text"), 240000)
        network_text = "\n".join(
            str(row.get("body") or "")
            for row in network_rows_list
            if isinstance(row, dict)
        )[:240000]
        title_text = " ".join(
            str(snap.get(key) or "")
            for key in ("title", "og_title", "og_description")
        )
        body_text = _safe(snap.get("body_text"), 80000)
        combined_lower = "\n".join((title_text, body_text, scripts, network_text)).lower()
        error_shell = any(marker in combined_lower for marker in ERROR_SHELL_MARKERS)
        observed = _observed_usernames(scripts + "\n" + network_text)
        meta_handles = _meta_handle(title_text)
        exact_structured = clean_handle in observed
        structured_mismatch = bool(observed) and clean_handle not in observed
        exact_meta = clean_handle in meta_handles
        canonical_match = service_module._canonical_matches(platform, clean_handle, snap.get("canonical"))
        final_url_match = _exact_profile_url(platform, clean_handle, snap.get("final_url"))

        sources = []
        if exact_structured:
            sources.append("structured_or_network_username")
        if exact_meta and canonical_match:
            sources.append("meta_username_plus_canonical")
        if exact_meta and final_url_match and bool(result.get("avatar_present")):
            sources.append("meta_username_plus_final_url_plus_avatar")
        # Telegram public pages commonly expose the exact @username in title/body
        # without JSON identity data.  Require the exact path as the second fact.
        if str(platform).lower() == "telegram" and exact_meta and (canonical_match or final_url_match):
            sources.append("telegram_exact_title_and_path")

        # Structured/network identity outranks decorative metadata.  If it names a
        # different account, retain that observed username for audit and discard any
        # weaker title/canonical coincidence so the profile fails closed.
        if structured_mismatch:
            sources = []
            observed_username = observed[0] if len(observed) == 1 else ""
        elif sources:
            observed_username = clean_handle
        else:
            observed_username = observed[0] if len(observed) == 1 else ""

        result["requested_handle"] = clean_handle
        result["observed_username"] = observed_username
        result["identity_sources"] = sources
        result["final_url_match"] = final_url_match
        result["identity_gate"] = "exact"

        if result.get("signal") == "exists":
            if error_shell or structured_mismatch or not sources:
                result.update({
                    "signal": "unknown",
                    "confidence": 0.0,
                    "username": "",
                    "username_exact": False,
                    "display_name": "",
                    "profile_id": "",
                    "avatar_present": False,
                    "avatar_url": "",
                    "bio_present": False,
                    "network_identity": False,
                    "detail": (
                        "Requested profile URL did not yield enough exact identity evidence; "
                        "error shells, redirects and canonical URLs alone do not prove occupancy"
                    ),
                })
        return result

    def search(query, handle, platform, snapshot, *, latency_ms=None):
        result = base_search(query, handle, platform, snapshot, latency_ms=latency_ms)
        exact_hits = []
        for hit in result.get("hits", []) if isinstance(result, dict) else []:
            if not isinstance(hit, dict):
                continue
            if _exact_profile_url(platform, service_module._clean_handle(handle), hit.get("url")):
                exact_hits.append(hit)
        result["hits"] = exact_hits[:5]
        result["exact_profile_hits"] = len(result["hits"])
        result["requested_profile_url"] = service_module.PROFILE_URLS.get(str(platform).lower(), "").format(
            handle=service_module._clean_handle(handle)
        ) if str(platform).lower() in service_module.PROFILE_URLS else ""
        result["url_match_policy"] = "exact_profile_path"
        return result

    profile._exact_identity_gate = True
    search._exact_identity_gate = True
    service_module.fingerprint_from_snapshot = profile
    service_module.search_fingerprint = search


__all__ = ["install_browser_eye_hardening"]
