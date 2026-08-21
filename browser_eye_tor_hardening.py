"""Security hardening for Browser Eye's optional Tor retrieval transport.

The Tor layer is retrieval-only. This module keeps it isolated from normal Browser
Eye traffic, rejects unsafe navigation targets and non-read HTTP methods, validates
redirect/subresource requests, bounds request fan-out, and never upgrades Tor
retrieval evidence into factual verification.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_PAGE_REQUESTS = 120
_ALLOWED_METHODS = {"GET", "HEAD"}
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "websocket", "eventsource"}
_SPECIAL_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".home.arpa")


def _forbidden_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not address.is_global


def _resolved_private(host: str, port: int, *, resolver=socket.getaddrinfo) -> bool:
    """Return True only when local DNS positively resolves a clearnet host privately.

    DNS failure is not treated as private because Tor may resolve a censored or
    locally-unresolvable public hostname at the exit. Literal/special private hosts
    are rejected before this function is reached.
    """
    try:
        rows = resolver(host, port, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror):
        return False
    addresses = []
    for row in rows or []:
        try:
            addresses.append(str(row[4][0]))
        except (IndexError, TypeError):
            continue
    return bool(addresses) and any(_forbidden_address(item) for item in addresses)


def safe_tor_url(value: object, *, resolver=socket.getaddrinfo) -> str:
    """Validate one Tor navigation target without pretending it is trustworthy."""
    raw = " ".join(str(value or "").split())[:2000]
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    try:
        port = parsed.port
    except ValueError:
        return ""
    if port not in {None, 80, 443}:
        return ""

    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(_SPECIAL_HOST_SUFFIXES):
        return ""

    # Tor v3 onion services are 56 base32 characters plus .onion. The Tor daemon
    # performs onion resolution; never leak them to local DNS.
    if host.endswith(".onion"):
        label = host[:-6]
        if len(label) != 56 or any(ch not in "abcdefghijklmnopqrstuvwxyz234567" for ch in label):
            return ""
        return raw

    if _forbidden_address(host):
        return ""
    effective_port = port or (443 if parsed.scheme == "https" else 80)
    if _resolved_private(host, effective_port, resolver=resolver):
        return ""
    return raw


def _request_is_read_only(method: object) -> bool:
    return str(method or "").upper() in _ALLOWED_METHODS


async def _guarded_route(route, *, runtime, counter: dict) -> None:
    request = route.request
    if not _request_is_read_only(request.method):
        await route.abort()
        return
    if request.resource_type in _BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return
    counter["count"] = int(counter.get("count", 0)) + 1
    if counter["count"] > MAX_PAGE_REQUESTS:
        await route.abort()
        return
    target = await asyncio.to_thread(safe_tor_url, request.url)
    if not target:
        await route.abort()
        return
    await runtime._route(route)


async def _hardened_search_engine(module, runtime, engine: str, query: str, limit: int) -> dict:
    context = await module._new_context(runtime)
    page = await context.new_page()
    counter = {"count": 0}

    async def guard(route):
        await _guarded_route(route, runtime=runtime, counter=counter)

    await page.route("**/*", guard)
    started = module.perf_counter()
    stage = "goto"
    try:
        target = safe_tor_url(module._engine_url(engine, query))
        if not target:
            raise ValueError("unsafe Tor search-engine target")
        response = await page.goto(target, wait_until="domcontentloaded", timeout=module.TOR_TIMEOUT_MS)
        status = response.status if response else None
        if status == 429:
            return {
                "engine": engine,
                "provider_status": "rate_limited",
                "results": [],
                "http_status": 429,
                "latency_ms": int((module.perf_counter() - started) * 1000),
            }
        stage = "settle"
        await page.wait_for_timeout(250)
        stage = "extract"
        snapshot = await module._extract_serp(page, engine)
        challenged = bool(snapshot.get("challenge"))
        rows = module.normalize_serp_rows(snapshot.get("rows"), limit)
        for row in rows:
            row["transport"] = "tor"
            row["onion_service"] = module.is_v3_onion_host(
                urlsplit(row.get("url") or "").hostname or ""
            )
        return {
            "engine": engine,
            "provider_status": "challenge" if challenged else "complete" if rows else "empty",
            "results": [] if challenged else rows,
            "http_status": status,
            "captcha": challenged,
            "request_count": counter["count"],
            "latency_ms": int((module.perf_counter() - started) * 1000),
        }
    except Exception as error:
        return {
            "engine": engine,
            "provider_status": "error",
            "results": [],
            "error_stage": stage,
            "error_code": module.classify_browser_error(error),
            "error_type": type(error).__name__,
            "latency_ms": int((module.perf_counter() - started) * 1000),
        }
    finally:
        await context.close()


async def _hardened_fetch(module, runtime, url: str) -> dict:
    target = safe_tor_url(url)
    if not target:
        raise ValueError("invalid Tor target URL")
    context = await module._new_context(runtime)
    page = await context.new_page()
    counter = {"count": 0}

    async def guard(route):
        await _guarded_route(route, runtime=runtime, counter=counter)

    await page.route("**/*", guard)
    started = module.perf_counter()
    try:
        response = await page.goto(target, wait_until="domcontentloaded", timeout=module.TOR_TIMEOUT_MS)
        headers = await response.all_headers() if response else {}
        content_type = str(headers.get("content-type") or "").lower()
        try:
            content_length = int(headers.get("content-length") or 0)
        except (TypeError, ValueError):
            content_length = 0
        if content_length > MAX_DOCUMENT_BYTES:
            return {
                "provider": "browser_eye_tor_fetch",
                "provider_status": "oversized",
                "transport": "tor",
                "requested_url": target,
                "http_status": response.status if response else None,
                "latency_ms": int((module.perf_counter() - started) * 1000),
                "verification": {"verified": False, "state": "tor_retrieval_rejected"},
            }
        if content_type and "html" not in content_type and "xhtml" not in content_type:
            return {
                "provider": "browser_eye_tor_fetch",
                "provider_status": "unsupported_content_type",
                "transport": "tor",
                "requested_url": target,
                "http_status": response.status if response else None,
                "latency_ms": int((module.perf_counter() - started) * 1000),
                "verification": {"verified": False, "state": "tor_retrieval_rejected"},
            }

        await page.wait_for_timeout(250)
        snapshot = await page.evaluate("""() => ({
          title: document.title || '',
          final_url: location.href,
          canonical: document.querySelector('link[rel="canonical"]')?.href || '',
          body_text: (document.body?.innerText || '').slice(0, 50000),
          links: [...document.querySelectorAll('a[href]')].slice(0, 80).map(a => ({
            url: a.href || '', title: (a.innerText || a.textContent || '').trim().slice(0, 240)
          }))
        })""")
        final_url = safe_tor_url(snapshot.get("final_url"))
        if not final_url:
            return {
                "provider": "browser_eye_tor_fetch",
                "provider_status": "blocked_redirect",
                "transport": "tor",
                "requested_url": target,
                "latency_ms": int((module.perf_counter() - started) * 1000),
                "verification": {"verified": False, "state": "tor_retrieval_rejected"},
            }
        host = (urlsplit(final_url).hostname or "").lower()
        onion_location = safe_tor_url(headers.get("onion-location") or "")
        safe_links = []
        for row in snapshot.get("links", []) if isinstance(snapshot.get("links"), list) else []:
            if not isinstance(row, dict):
                continue
            candidate = safe_tor_url(row.get("url"))
            if candidate:
                safe_links.append({"url": candidate, "title": module._clean(row.get("title"), 240)})
            if len(safe_links) >= 40:
                break
        return {
            "provider": "browser_eye_tor_fetch",
            "provider_status": "complete",
            "transport": "tor",
            "requested_url": target,
            "final_url": final_url,
            "host": host,
            "onion_service": module.is_v3_onion_host(host),
            "http_status": response.status if response else None,
            "title": module._clean(snapshot.get("title"), 300),
            "canonical": module._clean(snapshot.get("canonical"), module.MAX_URL),
            "description": module._clean(snapshot.get("body_text"), 1200),
            "body_text": module._clean(snapshot.get("body_text"), 50000),
            "links": safe_links,
            "onion_location": onion_location or None,
            "request_count": counter["count"],
            "latency_ms": int((module.perf_counter() - started) * 1000),
            "verification": {"verified": False, "state": "tor_retrieval_evidence"},
        }
    except Exception as error:
        return {
            "provider": "browser_eye_tor_fetch",
            "provider_status": "error",
            "transport": "tor",
            "requested_url": target,
            "error_code": module.classify_browser_error(error),
            "error_type": type(error).__name__,
            "latency_ms": int((module.perf_counter() - started) * 1000),
            "verification": {"verified": False, "state": "tor_retrieval_failed"},
        }
    finally:
        await context.close()


def install_tor_hardening(module) -> None:
    """Patch only Tor globals; normal Browser Eye runtime remains unchanged."""
    if getattr(module, "_namemachine_tor_hardening_installed", False):
        return
    module._namemachine_tor_hardening_installed = True
    original_diagnostics = module.tor_diagnostics

    module.safe_tor_url = safe_tor_url

    async def hardened_search(runtime, engine, query, limit):
        return await _hardened_search_engine(module, runtime, engine, query, limit)

    async def hardened_fetch(runtime, url):
        return await _hardened_fetch(module, runtime, url)

    def diagnostics():
        payload = dict(original_diagnostics())
        payload.update({
            "dns_private_resolution_guard": True,
            "redirect_and_subresource_guard": True,
            "read_only_methods": sorted(_ALLOWED_METHODS),
            "max_page_requests": MAX_PAGE_REQUESTS,
            "max_document_bytes": MAX_DOCUMENT_BYTES,
            "allowed_ports": [80, 443],
        })
        return payload

    module._search_engine_async = hardened_search
    module.tor_fetch_async = hardened_fetch
    module.tor_diagnostics = diagnostics


__all__ = [
    "MAX_DOCUMENT_BYTES",
    "MAX_PAGE_REQUESTS",
    "install_tor_hardening",
    "safe_tor_url",
]
