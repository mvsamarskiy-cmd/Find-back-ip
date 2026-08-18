import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote

import requests

HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "6"))
USER_AGENT = os.environ.get("HTTP_USER_AGENT", "Mozilla/5.0 (compatible; NameMachine/4.5)")
NAMECOM_CHECK_URL = "https://api.name.com/core/v1/domains:checkAvailability"
NAMECOM_SEARCH_URL = "https://www.name.com/domain/search"

STATUS_VALUES = (
    "claimable",
    "purchasable",
    "taken",
    "not_found",
    "invalid",
    "reserved",
    "rate_limited",
    "unknown",
)
ACTIONABLE_STATUSES = frozenset({"claimable", "purchasable"})
UNRESOLVED_STATUSES = frozenset({"rate_limited", "unknown"})


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
    offer=None,
):
    """Return one normalized status plus an auditable evidence record."""
    if status not in STATUS_VALUES:
        raise ValueError(f"Unsupported availability status: {status}")

    if occupancy is None:
        occupancy = {
            "taken": "occupied",
            "not_found": "not_found",
        }.get(status, "unknown")

    if claimability == "unconfirmed":
        claimability = {
            "claimable": "confirmed",
            "purchasable": "purchase_available",
            "taken": "not_claimable",
            "invalid": "not_claimable",
            "reserved": "not_claimable",
        }.get(status, claimability)

    result = {
        "status": status,
        "detail": detail,
        "url": url,
        "source": source,
        "method": method,
        "confidence": round(max(0.0, min(1.0, float(confidence))), 2),
        "occupancy": occupancy,
        "claimability": claimability,
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if offer is not None:
        result["offer"] = offer
    return result


def _namecom_offer(row, domain):
    """Keep only documented, non-secret fields from a Name.com result."""
    purchase_type = row.get("purchaseType") or "registration"
    offer = {
        "provider": "name.com",
        "domain_name": domain,
        "purchase_type": str(purchase_type),
        "premium": bool(row.get("premium", False)),
    }
    for source_key, output_key in (
        ("purchasePrice", "purchase_price"),
        ("renewalPrice", "renewal_price"),
    ):
        value = row.get(source_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            offer[output_key] = value
    reason = row.get("reason")
    if isinstance(reason, str) and reason.strip():
        offer["reason"] = reason.strip()[:300]
    return offer


def _check_namecom_registration(domain):
    """Confirm a fresh .com registration after RDAP reports no domain.

    Returning ``None`` means the optional integration is not configured. Once
    credentials are configured, every registrar outcome is returned explicitly
    so authentication, throttling, or malformed data cannot be hidden behind a
    false availability claim.
    """
    username = os.environ.get("NAMECOM_USERNAME", "").strip()
    token = os.environ.get("NAMECOM_API_TOKEN", "").strip()
    if not username or not token:
        return None

    method = "registrar_check_availability"
    try:
        response = requests.post(
            NAMECOM_CHECK_URL,
            auth=(username, token),
            json={"domainNames": [domain], "purchaseType": "registration"},
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        )
    except requests.RequestException as error:
        return _result(
            "unknown",
            f"RDAP found no registration; registrar error: {type(error).__name__}",
            NAMECOM_SEARCH_URL,
            source="namecom_core_api",
            method=method,
            confidence=0.9,
            occupancy="not_found",
        )

    if response.status_code == 429:
        return _result(
            "rate_limited",
            "RDAP found no registration; registrar rate limited the confirmation (429)",
            NAMECOM_SEARCH_URL,
            source="namecom_core_api",
            method=method,
            confidence=0.9,
            occupancy="not_found",
        )
    if response.status_code in (401, 403):
        return _result(
            "unknown",
            f"RDAP found no registration; registrar authentication unavailable ({response.status_code})",
            NAMECOM_SEARCH_URL,
            source="namecom_core_api",
            method=method,
            confidence=0.9,
            occupancy="not_found",
        )
    if response.status_code != 200:
        return _result(
            "unknown",
            f"RDAP found no registration; registrar HTTP {response.status_code}",
            NAMECOM_SEARCH_URL,
            source="namecom_core_api",
            method=method,
            confidence=0.9,
            occupancy="not_found",
        )

    try:
        payload = response.json()
    except (ValueError, TypeError):
        payload = None
    rows = payload.get("results") if isinstance(payload, dict) else None
    exact = next(
        (
            row for row in rows
            if isinstance(row, dict)
            and str(row.get("domainName", "")).lower() == domain
        ),
        None,
    ) if isinstance(rows, list) else None
    if exact is None:
        return _result(
            "unknown",
            "RDAP found no registration; registrar response omitted the exact domain",
            NAMECOM_SEARCH_URL,
            source="namecom_core_api",
            method=method,
            confidence=0.9,
            occupancy="not_found",
        )

    offer = _namecom_offer(exact, domain)
    if exact.get("purchasable") is True:
        if offer["premium"] or offer["purchase_type"] != "registration":
            return _result(
                "purchasable",
                "Name.com confirmed an authoritative purchase path after RDAP screening",
                NAMECOM_SEARCH_URL,
                source="namecom_core_api",
                method=method,
                confidence=0.99,
                occupancy="not_found",
                claimability="purchase_available",
                offer=offer,
            )
        return _result(
            "claimable",
            "Name.com confirmed standard .com registration after RDAP screening",
            NAMECOM_SEARCH_URL,
            source="namecom_core_api",
            method=method,
            confidence=0.99,
            occupancy="not_found",
            claimability="confirmed",
            offer=offer,
        )

    return _result(
        "unknown",
        "RDAP found no registration, but Name.com did not offer a standard registration",
        NAMECOM_SEARCH_URL,
        source="namecom_core_api",
        method=method,
        confidence=0.95,
        occupancy="not_found",
        offer=offer,
    )


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
            registrar = _check_namecom_registration(domain)
            if registrar is not None:
                return registrar
            return _result(
                "not_found", "Not found in .com RDAP; Name.com confirmation is not configured",
                public_url, source="verisign_rdap", method="rdap_exact_domain",
                confidence=0.9, occupancy="not_found",
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
                "not_found",
                "Public profile not found; claimability is not confirmed",
                url, confidence=0.72, occupancy="not_found",
            )
        if response.status_code == 200:
            text = response.text.lower()
            missing_markers = ("page isn't available", "sorry, this page isn't available")
            if any(marker in text for marker in missing_markers):
                return _result(
                    "not_found",
                    "Instagram page is unavailable; claimability is not confirmed",
                    url, confidence=0.62, occupancy="not_found",
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
        if response.status_code == 429:
            return _result("rate_limited", "Instagram rate limited the check (429)", url)
        if response.status_code in (401, 403):
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
                "not_found",
                "Public Telegram page not found; claimability is not confirmed",
                url, confidence=0.72, occupancy="not_found",
            )
        if response.status_code == 200:
            if "tgme_page_title" in text and "tgme_page_extra" in text:
                return _result(
                    "taken", "Public Telegram page exists", url,
                    confidence=0.85, occupancy="occupied", claimability="not_claimable",
                )
            return _result("unknown", "Telegram response inconclusive", url)
        if response.status_code == 429:
            return _result("rate_limited", "Telegram rate limited the check (429)", url)
        if response.status_code in (401, 403):
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
                "not_found",
                f"{platform} public profile not found; claimability is not confirmed",
                url, confidence=0.7, occupancy="not_found",
            )
        if response.status_code == 429:
            return _result("rate_limited", f"{platform} rate limited the check (429)", url)
        if response.status_code in (401, 403):
            return _result("unknown", f"{platform} blocked check ({response.status_code})", url)
        if response.status_code != 200:
            return _result("unknown", f"{platform} HTTP {response.status_code}", url)
        if any(marker.format(handle=handle) in text for marker in missing_markers):
            return _result(
                "not_found",
                f"{platform} reports no public profile; claimability is not confirmed",
                url, confidence=0.62, occupancy="not_found",
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
                    "not_found", "YouTube Data API found no channel; claimability is unconfirmed",
                    url, source="youtube_data_api", method="official_handle_lookup",
                    confidence=0.92, occupancy="not_found",
                )
            if response.status_code == 429:
                return _result(
                    "rate_limited", "YouTube API rate limited the check (429)", url,
                    source="youtube_data_api", method="official_handle_lookup",
                )
            if response.status_code == 403:
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
                    "not_found", "X API found no user; claimability is unconfirmed", url,
                    source="x_api", method="official_username_lookup",
                    confidence=0.92, occupancy="not_found",
                )
            if response.status_code == 429:
                return _result(
                    "rate_limited", "X API rate limited the check (429)", url,
                    source="x_api", method="official_username_lookup",
                )
            if response.status_code in (401, 403):
                return _result(
                    "unknown", f"X API unavailable ({response.status_code})", url,
                    source="x_api", method="official_username_lookup",
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
        result = {}
        for key, future in futures.items():
            try:
                result[key] = future.result()
            except Exception as error:
                result[key] = _result(
                    "unknown",
                    f"Internal checker error: {type(error).__name__}",
                    _public_url(key, name),
                    source="internal",
                    method="checker_error",
                )

    statuses = [value["status"] for value in result.values()]
    status_counts = {
        status: statuses.count(status)
        for status in STATUS_VALUES
    }
    claimable_count = status_counts["claimable"]
    purchasable_count = status_counts["purchasable"]
    actionable_count = sum(status_counts[status] for status in ACTIONABLE_STATUSES)
    unresolved_count = sum(status_counts[status] for status in UNRESOLVED_STATUSES)
    return {
        "availability": result,
        "status_counts": status_counts,
        "claimable_count": claimable_count,
        "purchasable_count": purchasable_count,
        "actionable_count": actionable_count,
        "not_found_count": status_counts["not_found"],
        "taken_count": status_counts["taken"],
        "invalid_count": status_counts["invalid"],
        "reserved_count": status_counts["reserved"],
        "rate_limited_count": status_counts["rate_limited"],
        "unknown_count": status_counts["unknown"],
        "unresolved_count": unresolved_count,
        "total_resources": len(checks),
        "all_claimable": claimable_count == len(checks),
        "all_verified": unresolved_count == 0,
        # Compatibility for API clients from before the evidence-status release.
        # Only confirmed actionable results count; ``not_found`` never does.
        "available_count": actionable_count,
        "all_available": actionable_count == len(checks),
    }


def _public_url(platform, name):
    handle = name.lower()
    return {
        "com": f"https://{handle}.com",
        "instagram": f"https://www.instagram.com/{handle}/",
        "telegram": f"https://t.me/{handle}",
        "tiktok": f"https://www.tiktok.com/@{handle}",
        "youtube": f"https://www.youtube.com/@{handle}",
        "facebook": f"https://www.facebook.com/{handle}",
        "x": f"https://x.com/{handle}",
    }[platform]


def check_many(names, max_workers=None):
    """Check several names concurrently while keeping outbound load bounded."""
    names = list(names)
    if not names:
        return []
    workers = max_workers or int(os.environ.get("AVAILABILITY_WORKERS", "8"))
    workers = max(1, min(workers, 12, len(names)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(check_all, names))
