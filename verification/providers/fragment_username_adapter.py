"""No-key Telegram username marketplace evidence from Fragment public pages.

Fragment can prove marketplace occupancy/availability and can expose a public TON
price or auction bid. A marketplace offer is *not* a free Telegram claim: the
adapter keeps that distinction while preserving price metadata for the UI/report.
"""
from __future__ import annotations

import html
import re
from time import perf_counter

import requests

from verification.models import Evidence

TIMEOUT = 6
BASE_URL = "https://fragment.com/username/{}"


def _number(value):
    text = html.unescape(str(value or "")).replace("\xa0", " ").strip()
    text = re.sub(r"[^0-9,.'\s]", "", text).replace("'", "")
    text = re.sub(r"\s+", "", text)
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        tail = text.rsplit(",", 1)[-1]
        text = text.replace(",", ".") if 0 < len(tail) <= 2 else text.replace(",", "")
    try:
        number = float(text)
    except ValueError:
        return None
    if number <= 0:
        return None
    return int(number) if number.is_integer() else round(number, 6)


def _marketplace_price_metadata(source):
    """Extract public TON price/bid labels without depending on one DOM layout."""
    source = str(source or "")
    visible = html.unescape(re.sub(r"<[^>]+>", " ", source))
    visible = re.sub(r"\s+", " ", visible).strip()
    output = {}
    patterns = (
        ("current_bid_ton", "current bid", r"current\s+bid\s*[:\-]?\s*([0-9][0-9\s,.'\u00a0]*)\s*ton\b"),
        ("minimum_bid_ton", "minimum bid", r"minimum\s+bid\s*[:\-]?\s*([0-9][0-9\s,.'\u00a0]*)\s*ton\b"),
        ("sold_price_ton", "sold for", r"sold(?:\s+for)?\s*[:\-]?\s*([0-9][0-9\s,.'\u00a0]*)\s*ton\b"),
        ("price_ton", "price", r"(?:buy\s+now|price)\s*[:\-]?\s*([0-9][0-9\s,.'\u00a0]*)\s*ton\b"),
    )
    for key, label, pattern in patterns:
        match = re.search(pattern, visible, flags=re.I)
        if not match:
            continue
        value = _number(match.group(1))
        if value is not None:
            output[key] = value
            output.setdefault("price_label", label)

    if not any(key.endswith("_ton") for key in output):
        for match in re.finditer(
            r'class=["\'][^"\']*(?:icon-ton|tm-value)[^"\']*["\'][^>]*>\s*([^<]{1,48})<',
            source,
            flags=re.I,
        ):
            value = _number(match.group(1))
            if value is None:
                continue
            context = html.unescape(re.sub(r"<[^>]+>", " ", source[max(0, match.start() - 320):match.end()]))
            lower = context.lower()
            if "current bid" in lower:
                key, label = "current_bid_ton", "current bid"
            elif "minimum bid" in lower or "minimum" in lower:
                key, label = "minimum_bid_ton", "minimum bid"
            elif "sold" in lower:
                key, label = "sold_price_ton", "sold for"
            else:
                key, label = "price_ton", "price"
            output[key] = value
            output.setdefault("price_label", label)
            break
    return output


def _evidence(handle, signal, detail, *, confidence=0.0, latency_ms=None, http_status=None, metadata=None):
    meta = {
        "no_api_key": True,
        "marketplace_signal": True,
        "positive_only": True,
        "authoritative_claimability": False,
        "marketplace_url": BASE_URL.format(handle),
    }
    if isinstance(metadata, dict):
        meta.update(metadata)
    return Evidence(
        platform="telegram",
        handle=handle,
        source="fragment_public_web",
        method="fragment_username_status",
        signal=signal,
        confidence=confidence,
        detail=detail,
        url=BASE_URL.format(handle),
        latency_ms=latency_ms,
        http_status=http_status,
        metadata=meta,
    ).to_dict()


def check_username(handle, platform="telegram"):
    handle = str(handle).strip().lower().lstrip("@")
    platform = str(platform).strip().lower()
    if platform != "telegram":
        return _evidence(handle, "unknown", "Fragment username probe supports Telegram only")

    if not (5 <= len(handle) <= 32) or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in handle):
        return _evidence(handle, "invalid", "Username does not match Telegram's documented basic username syntax", confidence=0.99)

    url = BASE_URL.format(handle)
    started = perf_counter()
    try:
        response = requests.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; NameMachine/6.9)",
                "Accept-Language": "en-US,en;q=0.8",
            },
        )
    except requests.RequestException as error:
        latency = int((perf_counter() - started) * 1000)
        return _evidence(handle, "unknown", f"Fragment public-page error: {type(error).__name__}", latency_ms=latency)

    latency = int((perf_counter() - started) * 1000)
    status = response.status_code
    if status == 429:
        return _evidence(handle, "rate_limited", "Fragment rate limited the username probe", latency_ms=latency, http_status=status)
    if status in (401, 403):
        return _evidence(handle, "unknown", f"Fragment blocked the username probe ({status})", latency_ms=latency, http_status=status)
    if status != 200:
        return _evidence(handle, "unknown", f"Fragment username page HTTP {status}", latency_ms=latency, http_status=status)

    text = response.text.lower()
    price = _marketplace_price_metadata(response.text)

    if 'status-taken">taken' in text or "status-taken'>taken" in text:
        return _evidence(
            handle,
            "exists",
            "Fragment explicitly marks the Telegram username as Taken",
            confidence=0.95,
            latency_ms=latency,
            http_status=status,
            metadata={"marketplace_status": "taken", **price},
        )

    if ('status-unavail">sold' in text or "status-unavail'>sold" in text or
            'status-sold">sold' in text or "status-sold'>sold" in text):
        return _evidence(
            handle,
            "reserved",
            "Fragment marks the collectible username as Sold",
            confidence=0.97,
            latency_ms=latency,
            http_status=status,
            metadata={"marketplace_status": "sold", **price},
        )

    if 'status-avail">available' in text or "status-avail'>available" in text:
        return _evidence(
            handle,
            "purchasable",
            "Fragment exposes the username as available through its marketplace",
            confidence=0.9,
            latency_ms=latency,
            http_status=status,
            metadata={"marketplace_status": "available", **price},
        )

    return _evidence(
        handle,
        "unknown",
        "Fragment returned no safe positive username status",
        latency_ms=latency,
        http_status=status,
        metadata=price,
    )


__all__ = ["_marketplace_price_metadata", "check_username"]
