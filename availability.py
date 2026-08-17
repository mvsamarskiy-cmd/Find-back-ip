import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "4"))
USER_AGENT = os.environ.get("HTTP_USER_AGENT", "NameMachine/3.0")


def _result(status, detail, url):
    return {"status": status, "detail": detail, "url": url}


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
            return _result("taken", "Registered in .com RDAP", public_url)
        if response.status_code == 404:
            return _result("available", "Not found in .com RDAP", public_url)
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
            return _result("available", "Profile returned 404", url)
        if response.status_code == 200:
            text = response.text.lower()
            missing_markers = ("page isn't available", "sorry, this page isn't available")
            if any(marker in text for marker in missing_markers):
                return _result("available", "Instagram reports page unavailable", url)
            # A generic HTTP 200 may be a login/challenge page, so it is not
            # sufficient evidence that the requested handle exists.
            handle = name.lower()
            profile_markers = (f'\"username\":\"{handle}\"', f'@{handle}')
            if any(marker in text for marker in profile_markers):
                return _result("taken", "Public profile page exists", url)
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
            return _result("available", "Telegram returned 404", url)
        if response.status_code == 200:
            if "tgme_page_title" in text and "tgme_page_extra" in text:
                return _result("taken", "Public Telegram page exists", url)
            return _result("unknown", "Telegram response inconclusive", url)
        if response.status_code in (401, 403, 429):
            return _result("unknown", f"Telegram blocked check ({response.status_code})", url)
        return _result("unknown", f"Telegram HTTP {response.status_code}", url)
    except requests.RequestException as error:
        return _result("unknown", f"Telegram error: {type(error).__name__}", url)


def check_all(name):
    checks = {
        "com": check_com,
        "instagram": check_instagram,
        "telegram": check_telegram,
    }
    with ThreadPoolExecutor(max_workers=len(checks)) as executor:
        futures = {key: executor.submit(check, name) for key, check in checks.items()}
        result = {key: future.result() for key, future in futures.items()}

    statuses = [value["status"] for value in result.values()]
    return {
        "availability": result,
        "all_available": all(status == "available" for status in statuses),
        "all_verified": all(status != "unknown" for status in statuses),
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
