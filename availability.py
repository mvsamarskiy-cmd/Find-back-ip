import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote

import requests

HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "6"))
USER_AGENT = os.environ.get("HTTP_USER_AGENT", "Mozilla/5.0 (compatible; NameMachine/4.1)")


def _result(
    status,
    detail,
    url,
    *,
    source="public_web",
    method="public_profile",
    confidence=0.0,
    occupancy=None,
    claimability="unconfirmed",
):
    """Return a backward-compatible result plus an auditable evidence record.

    ``status`` remains available for the current UI.  Occupancy and
    claimability are deliberately separate: an account can be absent from the
    public web while its username is reserved or otherwise impossible to
    claim.
    """
    return {
        "status": status,
        "detail": detail,
        "url": url,
        "source": source,
        "method": method,
        "confidence": round(max(0.0, min(1.0, float(confidence))), 2),
        "occupancy": occupancy or ("occupied" if status == "taken" else "unknown"),
        "claimability": claimability,
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def check_com(name):
    domain = f"{name.lower()}.com"
    public_url = f"https://{domain}"
    rdap_url = f"https://rdap.verisign.com/com/v1/domain/{quote(domain)}"
    try:
        response = requests.get(
            rdap_url,
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code == 200:
            return _result(
                "taken", "Registered in .com RDAP", public_url,
                source="verisign_rdap", method="rdap_exact_domain",
                confidence=0.99, occupancy="occupied", claimability="not_claimable",
            )
        if response.status_code == 404:
            return _result(
                "available", "Not found in .com RDAP; registrar purchase is not confirmed",
                public_url, source="verisign_rdap", method="rdap_exact_domain",
                confidence=0.9, occupancy="not_found", claimability="likely",
            )
        return _result("unknown", f"RDAP HTTP {response.status_code}", public_url)
    except requests.RequestException as error:
        return _result("unknown", f"RDAP error: {type(error).__name__}", public_url)


def check_instagram(name):
    url = f"https://www.instagram.com/{name.lower()}/"
    try:
        response = requests.get(
            url,
            timeout=HTTP_TIMEOUT,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if response.status_code == 404:
            return _result(
                "unknown",
                "Public profile not found; claimability is not confirmed",
                url,
            )
        if response.status_code == 200:
            text = response.text.lower()
            missing_markers = ("page isn't available", "sorry, this page isn't available")
            if any(marker in text for marker in missing_markers):
                return _result(
                    "unknown",
                    "Instagram page is unavailable; claimability is not confirmed",
                    url,
                )
            # A generic HTTP 200 may be a login/challenge page, so it is not
            # sufficient evidence that the requested handle exists.
            handle = name.lower()
            profile_markers = (f'\"username\":\"{handle}\"', f'@{handle}')
            if any(marker in text for marker in profile_markers):
                return _result(
                    "taken", "Exact username found in public profile page", url,
                    confidence=0.82, occupancy="occupied", claimability="not_claimable",
                )
            return _result("unknown", "Instagram response inconclusive", url)
        if response.status_code in (401, 403, 429):
            return _result("unknown", f"Instagram blocked check ({response.status_code})", url)
        return _result("unknown", f"Instagram HTTP {response.status_code}", url)
    except requests.RequestException as error:
        return _result("unknown", f"Instagram error: {type(error).__name__}", url)


def check_telegram(name):
    url = f"https://t.me/{name.lower()}"
    try:
        response = requests.get(
            url,
            timeout=HTTP_TIMEOUT,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        text = response.text.lower()
        if response.status_code == 404:
            return _result(
                "unknown",
                "Public Telegram page not found; claimability is not confirmed",
                url,
            )
        if response.status_code == 200:
            if "tgme_page_title" in text and "tgme_page_extra" in text:
                return _result(
                    "taken", "Public Telegram page exists", url,
                    confidence=0.85, occupancy="occupied", claimability="not_claimable",
                )
            return _result("unknown", "Telegram response inconclusive", url)
        if response.status_code in (401, 403, 429):
            return _result("unknown", f"Telegram blocked check ({response.status_code})", url)
        return _result("unknown", f"Telegram HTTP {response.status_code}", url)
    except requests.RequestException as error:
        return _result("unknown", f"Telegram error: {type(error).__name__}", url)


def _check_public_profile(name, platform, url, taken_markers=(), missing_markers=()):
    """Classify public evidence without equating absence with claimability.

    Social platforms can return a 404 or a missing-account page for blocked,
    reserved, suspended, localized, or otherwise unavailable handles. Those
    responses are useful evidence that no public profile was observed, but
    they do not prove the handle can be claimed.
    """
    handle = name.lower()
    try:
        response = requests.get(
            url, timeout=HTTP_TIMEOUT, allow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.8"},
        )
        text = response.text.lower()
        if response.status_code == 404:
            return _result(
                "unknown",
                f"{platform} public profile not found; claimability is not confirmed",
                url,
            )
        if response.status_code in (401, 403, 429):
            return _result("unknown", f"{platform} blocked check ({response.status_code})", url)
        if response.status_code != 200:
            return _result("unknown", f"{platform} HTTP {response.status_code}", url)
        if any(marker.format(handle=handle) in text for marker in missing_markers):
            return _result(
                "unknown",
                f"{platform} reports no public profile; claimability is not confirmed",
                url,
            )
        if any(marker.format(handle=handle) in text for marker in taken_markers):
            return _result(
                "taken", f"Exact username found in public {platform} profile", url,
                confidence=0.8, occupancy="occupied", claimability="not_claimable",
            )
        return _result("unknown", f"{platform} response inconclusive", url)
    except requests.RequestException as error:
        return _result("unknown", f"{platform} error: {type(error).__name__}", url)


def check_tiktok(name):
    handle = name.lower()
    return _check_public_profile(
        name, "TikTok", f"https://www.tiktok.com/@{handle}",
        ('"uniqueid":"{handle}"', '@{handle} | tiktok'),
        ("couldn't find this account", "couldn’t find this account"),
    )


def check_youtube(name):
    handle = name.lower()
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if api_key:
        url = f"https://www.youtube.com/@{handle}"
        try:
            response = requests.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "id,snippet", "forHandle": handle, "key": api_key},
                timeout=HTTP_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )
            if response.status_code == 200:
                payload = response.json()
                if payload.get("items"):
                    return _result(
                        "taken", "YouTube Data API found the exact handle", url,
                        source="youtube_data_api", method="official_handle_lookup",
                        confidence=0.99, occupancy="occupied", claimability="not_claimable",
                    )
                return _result(
                    "unknown", "YouTube Data API found no channel; claimability is unconfirmed",
                    url, source="youtube_data_api", method="official_handle_lookup",
                    confidence=0.92, occupancy="not_found",
                )
            if response.status_code in (403, 429):
                return _result(
                    "unknown", f"YouTube API unavailable ({response.status_code})", url,
                    source="youtube_data_api", method="official_handle_lookup",
                )
        except (requests.RequestException, ValueError):
            pass
    return _check_public_profile(
        name, "YouTube", f"https://www.youtube.com/@{handle}",
        ('"canonicalbaseurl":"/@{handle}"', 'youtube.com/@{handle}'),
        ("this page isn't available", "404 not found"),
    )


def check_facebook(name):
    handle = name.lower()
    return _check_public_profile(
        name, "Facebook", f"https://www.facebook.com/{handle}",
        ('"vanity":"{handle}"', 'facebook.com/{handle}'),
        ("this content isn't available", "page isn't available"),
    )


def check_x(name):
    handle = name.lower()
    bearer = os.environ.get("X_BEARER_TOKEN", "").strip()
    if bearer:
        url = f"https://x.com/{handle}"
        try:
            response = requests.get(
                f"https://api.x.com/2/users/by/username/{quote(handle)}",
                timeout=HTTP_TIMEOUT,
                headers={"Authorization": f"Bearer {bearer}", "User-Agent": USER_AGENT},
            )
            if response.status_code == 200 and response.json().get("data"):
                return _result(
                    "taken", "X API found the exact username", url,
                    source="x_api", method="official_username_lookup",
                    confidence=0.99, occupancy="occupied", claimability="not_claimable",
                )
            if response.status_code == 404:
                return _result(
                    "unknown", "X API found no user; claimability is unconfirmed", url,
                    source="x_api", method="official_username_lookup",
                    confidence=0.92, occupancy="not_found",
                )
        except (requests.RequestException, ValueError):
            pass
    return _check_public_profile(
        name, "X", f"https://x.com/{handle}",
        ('"screen_name":"{handle}"', '@{handle} / x'),
        ("this account doesn’t exist", "this account doesn't exist"),
    )


def check_all(name):
    checks = {
        "com": check_com,
        "instagram": check_instagram,
        "telegram": check_telegram,
        "tiktok": check_tiktok,
        "youtube": check_youtube,
        "facebook": check_facebook,
        "x": check_x,
    }
    with ThreadPoolExecutor(max_workers=len(checks)) as executor:
        futures = {key: executor.submit(check, name) for key, check in checks.items()}
        result = {key: future.result() for key, future in futures.items()}

    statuses = [value["status"] for value in result.values()]
    available_count = sum(status == "available" for status in statuses)
    taken_count = sum(status == "taken" for status in statuses)
    unknown_count = sum(status == "unknown" for status in statuses)
    return {
        "availability": result,
        "available_count": available_count,
        "taken_count": taken_count,
        "unknown_count": unknown_count,
        "total_resources": len(checks),
        "all_available": available_count == len(checks),
        "all_verified": unknown_count == 0,
    }


def check_many(names, max_workers=None):
    """Check several names concurrently while keeping outbound load bounded."""
    names = list(names)
    if not names:
        return []
    workers = max_workers or int(os.environ.get("AVAILABILITY_WORKERS", "8"))
    workers = max(1, min(workers, 12, len(names)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(check_all, names))
