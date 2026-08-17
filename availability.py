from urllib.parse import quote
import os
import requests

HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "4"))
USER_AGENT = os.environ.get("HTTP_USER_AGENT", "NameMachine/3.0")


def check_com(name):
    domain = f"{name.lower()}.com"
    url = f"https://rdap.verisign.com/com/v1/domain/{quote(domain)}"
    try:
        r = requests.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
        if r.status_code == 200:
            return {"status": "taken", "detail": "Registered in .com RDAP", "url": f"https://{domain}"}
        if r.status_code == 404:
            return {"status": "available", "detail": "Not found in .com RDAP", "url": f"https://{domain}"}
        return {"status": "unknown", "detail": f"RDAP HTTP {r.status_code}", "url": f"https://{domain}"}
    except requests.RequestException as e:
        return {"status": "unknown", "detail": f"RDAP error: {type(e).__name__}", "url": f"https://{domain}"}


def check_instagram(name):
    handle = name.lower()
    url = f"https://www.instagram.com/{handle}/"
    try:
        r = requests.get(url, timeout=HTTP_TIMEOUT, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 404:
            return {"status": "available", "detail": "Profile returned 404", "url": url}
        if r.status_code == 200:
            text = r.text.lower()
            if "page isn't available" in text or "sorry, this page isn't available" in text:
                return {"status": "available", "detail": "Instagram reports page unavailable", "url": url}
            return {"status": "taken", "detail": "Public profile page exists", "url": url}
        if r.status_code in (401, 403, 429):
            return {"status": "unknown", "detail": f"Instagram blocked check ({r.status_code})", "url": url}
        return {"status": "unknown", "detail": f"Instagram HTTP {r.status_code}", "url": url}
    except requests.RequestException as e:
        return {"status": "unknown", "detail": f"Instagram error: {type(e).__name__}", "url": url}


def check_telegram(name):
    handle = name.lower()
    url = f"https://t.me/{handle}"
    try:
        r = requests.get(url, timeout=HTTP_TIMEOUT, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        text = r.text.lower()
        if r.status_code == 404:
            return {"status": "available", "detail": "Telegram returned 404", "url": url}
        if r.status_code == 200:
            markers = ("view in telegram", "tgme_page_title", "tgme_page_extra")
            if any(m in text for m in markers):
                return {"status": "taken", "detail": "Public Telegram page exists", "url": url}
            return {"status": "unknown", "detail": "Telegram response inconclusive", "url": url}
        if r.status_code in (401, 403, 429):
            return {"status": "unknown", "detail": f"Telegram blocked check ({r.status_code})", "url": url}
        return {"status": "unknown", "detail": f"Telegram HTTP {r.status_code}", "url": url}
    except requests.RequestException as e:
        return {"status": "unknown", "detail": f"Telegram error: {type(e).__name__}", "url": url}


def check_all(name):
    result = {
        "com": check_com(name),
        "instagram": check_instagram(name),
        "telegram": check_telegram(name),
    }
    statuses = [v["status"] for v in result.values()]
    return {
        "availability": result,
        "all_available": all(s == "available" for s in statuses),
        "all_verified": all(s != "unknown" for s in statuses),
    }
