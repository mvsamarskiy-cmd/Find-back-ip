import os
from urllib.parse import quote

import requests


ALLOWED_MTProto_STATUSES = frozenset({"occupied", "not_found", "reserved", "unknown"})
ALLOWED_FRAGMENT_STATUSES = frozenset({"for_sale", "occupied", "not_found", "reserved", "unknown"})


def _clean_text(value, limit=300):
    return " ".join(str(value or "").split())[:limit]


def _clean_price(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return value
    return None


def _normalize_payload(payload, expected_username):
    """Validate the narrow contract returned by the secured Telegram service."""
    if not isinstance(payload, dict):
        raise ValueError("Telegram evidence response must be an object")

    username = _clean_text(payload.get("username"), 32).lower().lstrip("@")
    if username != expected_username.lower():
        raise ValueError("Telegram evidence response does not match requested username")

    mtproto = payload.get("mtproto")
    fragment = payload.get("fragment")
    if not isinstance(mtproto, dict) or not isinstance(fragment, dict):
        raise ValueError("Telegram evidence response is missing mtproto/fragment evidence")

    mtproto_status = _clean_text(mtproto.get("status"), 30).lower()
    fragment_status = _clean_text(fragment.get("status"), 30).lower()
    if mtproto_status not in ALLOWED_MTProto_STATUSES:
        raise ValueError("Unsupported MTProto evidence status")
    if fragment_status not in ALLOWED_FRAGMENT_STATUSES:
        raise ValueError("Unsupported Fragment evidence status")

    fragment_url = _clean_text(fragment.get("url"), 500)
    if fragment_url and not fragment_url.startswith("https://fragment.com/"):
        fragment_url = ""

    return {
        "username": username,
        "mtproto": {
            "status": mtproto_status,
            "detail": _clean_text(mtproto.get("detail")),
        },
        "fragment": {
            "status": fragment_status,
            "detail": _clean_text(fragment.get("detail")),
            "url": fragment_url or f"https://fragment.com/username/{quote(username)}",
            "price": _clean_price(fragment.get("price")),
            "currency": _clean_text(fragment.get("currency"), 12).upper(),
        },
    }


def fetch_telegram_evidence(username, *, timeout=6.0):
    """Query an optional secured Telegram evidence service.

    The main web process never stores a Telegram user session. Operators can point
    TELEGRAM_EVIDENCE_URL at a separately isolated service that owns MTProto
    credentials/session state and, when permitted, Fragment observations.

    Returns None when the integration is not configured. Otherwise returns a
    small transport envelope so callers can preserve rate-limit/auth failures as
    explicit unknown evidence instead of silently falling back to weaker web data.
    """
    base_url = os.environ.get("TELEGRAM_EVIDENCE_URL", "").strip().rstrip("/")
    token = os.environ.get("TELEGRAM_EVIDENCE_TOKEN", "").strip()
    if not base_url or not token:
        return None
    if not base_url.startswith("https://"):
        return {"transport_status": "configuration_error", "detail": "Telegram evidence URL must use HTTPS"}

    handle = username.lower().lstrip("@")
    url = f"{base_url}/v1/username/{quote(handle)}"
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "NameMachine/telegram-evidence-client",
            },
        )
    except requests.RequestException as error:
        return {
            "transport_status": "network_error",
            "detail": f"Telegram evidence service error: {type(error).__name__}",
        }

    if response.status_code == 429:
        return {"transport_status": "rate_limited", "detail": "Telegram evidence service rate limited the request"}
    if response.status_code in (401, 403):
        return {"transport_status": "auth_error", "detail": "Telegram evidence service authentication failed"}
    if response.status_code != 200:
        return {
            "transport_status": "http_error",
            "detail": f"Telegram evidence service HTTP {response.status_code}",
        }

    try:
        payload = response.json()
        evidence = _normalize_payload(payload, handle)
    except (ValueError, TypeError) as error:
        return {
            "transport_status": "malformed",
            "detail": f"Telegram evidence service returned invalid data: {type(error).__name__}",
        }
    return {"transport_status": "ok", "evidence": evidence}
