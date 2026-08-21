"""Read-only evidence fetch and public-contact extraction for private research mode.

The module preserves the original source URL and rendered page text as evidence.
It does not log in, submit forms, contact people, purchase anything, or promote
retrieval evidence into verified fact. Direct page retrieval is delegated to the
hardened Browser Eye Tor transport so clearnet and v3 onion URLs share one policy.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

import requests


EVIDENCE_VERSION = "journalist-evidence-v1"
CONTACT_EXTRACTION_VERSION = "public-contact-extraction-v1"
MAX_SOURCE_URL = 2000
MAX_BODY_TEXT = 50_000
MAX_LINKS = 80

_EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]{1,64}@[A-Z0-9.-]{1,190}\.[A-Z]{2,24})(?![\w.-])", re.I)
_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s()./-]{5,22}\d)(?!\w)")
_TELEGRAM_TEXT_RE = re.compile(r"\btelegram\s*(?:[:=\-]|at)?\s*@?([A-Za-z0-9_]{5,32})\b", re.I)
_MATRIX_ID_RE = re.compile(r"(?<!\w)(@[A-Za-z0-9._=\-/]+:[A-Za-z0-9.-]+)(?!\w)")
_XMPP_TEXT_RE = re.compile(r"\bxmpp\s*:\s*([^\s<>]{3,254})", re.I)
_ONION_RE = re.compile(r"\b(?:https?://)?([a-z2-7]{56}\.onion)(?:/[^\s<>\"']*)?", re.I)


def _clean(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _raw_text(value: object, limit: int = MAX_BODY_TEXT) -> str:
    text = str(value or "")
    return text[:limit]


def _unique(values, limit=100):
    output = []
    seen = set()
    for value in values:
        item = str(value or "").strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    return output


def _valid_phone(observed: str) -> bool:
    digits = re.sub(r"\D", "", observed or "")
    return 7 <= len(digits) <= 15


def _link_kind(url: str) -> str:
    raw = str(url or "").strip()
    lower = raw.casefold()
    if lower.startswith("mailto:"):
        return "email"
    if lower.startswith("tel:"):
        return "phone"
    if lower.startswith("xmpp:"):
        return "xmpp"
    if lower.startswith("tg:"):
        return "telegram"
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return "other"
    host = (parsed.hostname or "").lower()
    if host.endswith(".onion"):
        return "onion"
    if host in {"t.me", "telegram.me", "www.t.me", "www.telegram.me"}:
        return "telegram"
    if host.endswith("signal.me"):
        return "signal"
    if host.endswith("matrix.to"):
        return "matrix"
    if parsed.scheme in {"http", "https"}:
        return "web"
    return "other"


def _public_links(rows: object) -> list[dict]:
    output = []
    seen = set()
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or "").strip()[:MAX_SOURCE_URL]
        title = str(raw.get("title") or "").strip()[:240]
        if not url:
            continue
        kind = _link_kind(url)
        if kind == "other":
            continue
        key = url.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append({"url": url, "title": title, "kind": kind})
        if len(output) >= MAX_LINKS:
            break
    return output


def extract_public_contacts(body_text: object, links: object = None) -> dict:
    """Extract only contact identifiers visibly present in the retrieved source."""
    text = _raw_text(body_text)
    public_links = _public_links(links)

    emails = [match.group(1) for match in _EMAIL_RE.finditer(text)]
    phones = [match.group(1).strip() for match in _PHONE_RE.finditer(text) if _valid_phone(match.group(1))]
    telegram = ["@" + match.group(1) for match in _TELEGRAM_TEXT_RE.finditer(text)]
    matrix = [match.group(1) for match in _MATRIX_ID_RE.finditer(text)]
    xmpp = [match.group(1) for match in _XMPP_TEXT_RE.finditer(text)]
    onions = [match.group(0) for match in _ONION_RE.finditer(text)]
    signal = []

    for row in public_links:
        url = row["url"]
        kind = row["kind"]
        if kind == "email":
            emails.append(unquote(url[7:].split("?", 1)[0]))
        elif kind == "phone":
            observed = unquote(url[4:].split("?", 1)[0])
            if _valid_phone(observed):
                phones.append(observed)
        elif kind == "telegram":
            telegram.append(url)
        elif kind == "signal":
            signal.append(url)
        elif kind == "matrix":
            matrix.append(url)
        elif kind == "xmpp":
            xmpp.append(url)
        elif kind == "onion":
            onions.append(url)

    return {
        "version": CONTACT_EXTRACTION_VERSION,
        "scope": "publicly_observed_source_content_only",
        "emails": _unique(emails, 60),
        "phones": _unique(phones, 60),
        "telegram": _unique(telegram, 60),
        "signal": _unique(signal, 60),
        "matrix": _unique(matrix, 60),
        "xmpp": _unique(xmpp, 60),
        "onion_urls": _unique(onions, 80),
    }


def _provider_config() -> tuple[str, str]:
    browser_url = str(os.environ.get("BROWSER_EYE_URL") or "").strip().rstrip("/")
    browser_token = str(os.environ.get("GLOBAL_SEARCH_BROWSER_TOKEN") or "").strip()
    return browser_url, browser_token


def _snapshot_sha256(final_url: str, title: str, body_text: str) -> str:
    payload = "\n".join((final_url, title, body_text)).encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()


def fetch_research_evidence(url: object, *, poster=requests.post) -> dict:
    requested_url = str(url or "").strip()[:MAX_SOURCE_URL]
    if not requested_url:
        raise ValueError("Source URL is required")
    try:
        parsed = urlsplit(requested_url)
    except ValueError as error:
        raise ValueError("Invalid source URL") from error
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only http(s) source URLs are supported")

    browser_url, browser_token = _provider_config()
    if not browser_url or not browser_token:
        return {
            "version": EVIDENCE_VERSION,
            "provider_status": "unconfigured",
            "requested_url": requested_url,
            "truth_semantics": "source_retrieval_not_fact_verification",
        }

    response = poster(
        browser_url + "/v1/tor-fetch",
        json={"url": requested_url},
        timeout=22,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "NameMachine-journalist-evidence/1",
            "X-Global-Search-Token": browser_token,
        },
    )
    if response.status_code == 429:
        return {"version": EVIDENCE_VERSION, "provider_status": "rate_limited", "requested_url": requested_url}
    if response.status_code != 200:
        return {
            "version": EVIDENCE_VERSION,
            "provider_status": f"provider_http_{response.status_code}",
            "requested_url": requested_url,
        }

    payload = response.json() if response.content else {}
    if not isinstance(payload, dict):
        payload = {}
    status = str(payload.get("provider_status") or "complete")
    body_text = _raw_text(payload.get("body_text"))
    title = str(payload.get("title") or "")[:300]
    final_url = str(payload.get("final_url") or requested_url)[:MAX_SOURCE_URL]
    links = _public_links(payload.get("links"))
    contacts = extract_public_contacts(body_text, links)
    observed_at = datetime.now(timezone.utc).isoformat()

    return {
        "version": EVIDENCE_VERSION,
        "provider_status": status,
        "transport": "tor",
        "requested_url": requested_url,
        "final_url": final_url,
        "canonical": str(payload.get("canonical") or "")[:MAX_SOURCE_URL],
        "host": str(payload.get("host") or "")[:260],
        "onion_service": bool(payload.get("onion_service")),
        "onion_location": str(payload.get("onion_location") or "")[:MAX_SOURCE_URL] or None,
        "http_status": payload.get("http_status"),
        "title": title,
        "body_text": body_text,
        "description": _clean(payload.get("description"), 1200),
        "links": links,
        "public_contacts": contacts,
        "observed_at": observed_at,
        "snapshot_sha256": _snapshot_sha256(final_url, title, body_text),
        "source_preserved": True,
        "actions_performed": ["read_only_get"],
        "verification": {"verified": False, "state": "retrieved_source_evidence"},
        "truth_semantics": "source_retrieval_not_fact_verification",
    }


def research_evidence_capabilities() -> dict:
    browser_url, browser_token = _provider_config()
    return {
        "version": EVIDENCE_VERSION,
        "configured": bool(browser_url and browser_token),
        "transport": "tor",
        "clearnet_over_tor": True,
        "v3_onion": True,
        "original_url_preserved": True,
        "full_text_max_chars": MAX_BODY_TEXT,
        "outbound_link_max": MAX_LINKS,
        "public_contact_extraction": True,
        "public_contact_scope": "source_content_only",
        "login_automation": False,
        "form_submission": False,
        "purchase_automation": False,
        "truth_semantics": "source_retrieval_not_fact_verification",
    }


__all__ = [
    "CONTACT_EXTRACTION_VERSION",
    "EVIDENCE_VERSION",
    "extract_public_contacts",
    "fetch_research_evidence",
    "research_evidence_capabilities",
]
