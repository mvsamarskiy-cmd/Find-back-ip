"""Tor-backed read-only retrieval for the private Browser Eye service.

This module is intentionally additive. Normal Browser Eye profile verification and
normal web search keep their existing transports. Tor is used only when an internal
caller explicitly requests the Tor route. The route performs rendered GET-only
retrieval, blocks downloads/heavy assets, preserves provenance, and never upgrades
retrieval evidence into a verified financial/opportunity fact.
"""
from __future__ import annotations

import asyncio
import hmac
import ipaddress
import os
import re
import socket
from time import perf_counter, sleep
from urllib.parse import quote_plus, urlsplit

from flask import jsonify, request

from browser_eye_global_search import classify_browser_error, normalize_serp_rows


TOR_TRANSPORT_VERSION = "tor-opportunity-transport-v1"
MAX_RESULTS = 20
MAX_QUERY = 1800
MAX_URL = 2000
TOR_TIMEOUT_MS = 9000
TOR_SEARCH_ENGINES = ("duckduckgo", "bing", "google")
_ONION_V3_RE = re.compile(r"^[a-z2-7]{56}\.onion$", re.I)


def _clean(value, limit=1200):
    return " ".join(str(value or "").split())[:limit]


def _enabled():
    return str(os.environ.get("TOR_SEARCH_ENABLED", "0")).strip().casefold() in {"1", "true", "yes", "on"}


def _proxy_server():
    value = str(os.environ.get("TOR_SOCKS_PROXY") or "socks5://127.0.0.1:9050").strip()
    return value if value.startswith("socks5://") else ""


def _authorized():
    expected = str(os.environ.get("GLOBAL_SEARCH_BROWSER_TOKEN") or "").strip()
    supplied = str(request.headers.get("X-Global-Search-Token") or "").strip()
    return bool(expected and supplied) and hmac.compare_digest(supplied, expected)


def is_v3_onion_host(host: object) -> bool:
    return bool(_ONION_V3_RE.fullmatch(str(host or "").strip().lower()))


def safe_tor_url(value: object) -> str:
    raw = _clean(value, MAX_URL)
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
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return ""
    if host.endswith(".onion"):
        return raw if is_v3_onion_host(host) else ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return ""
    return raw


def _proxy_host_port():
    proxy = _proxy_server()
    try:
        parsed = urlsplit(proxy)
    except ValueError:
        return None
    if parsed.scheme != "socks5" or not parsed.hostname or not parsed.port:
        return None
    return parsed.hostname, parsed.port


def tor_socket_ready(timeout: float = 0.2) -> bool:
    target = _proxy_host_port()
    if not _enabled() or not target:
        return False
    host, port = target
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_tor_socket(timeout: float = 8.0) -> bool:
    if not _enabled():
        return True
    deadline = perf_counter() + max(0.1, timeout)
    while perf_counter() < deadline:
        if tor_socket_ready(timeout=0.15):
            return True
        sleep(0.1)
    return False


def tor_diagnostics() -> dict:
    return {
        "version": TOR_TRANSPORT_VERSION,
        "enabled": _enabled(),
        "socks5_configured": bool(_proxy_server()),
        "socket_ready": tor_socket_ready(),
        "read_only_get": True,
        "downloads_allowed": False,
        "onion_v3_only": True,
        "onion_location_discovery": True,
        "generic_web_over_tor": True,
        "direct_source_verification": False,
        "truth_semantics": "tor_retrieval_evidence_not_verified_fact",
    }


def _engine_url(engine: str, query: str) -> str:
    encoded = quote_plus(query)
    if engine == "bing":
        return f"https://www.bing.com/search?q={encoded}&count=20&setlang=en"
    if engine == "google":
        return f"https://www.google.com/search?q={encoded}&num=20&hl=en"
    return f"https://html.duckduckgo.com/html/?q={encoded}"


async def _extract_serp(page, engine: str):
    return await page.evaluate(
        """(engine) => {
          const bodyText = document.body?.innerText || '';
          const challenge = /unusual traffic|captcha|verify (you are|you're) human|one last step|security check|automated queries/i.test(bodyText);
          const rows = [];
          const push = (a, box, snippetNode) => {
            if (!a) return;
            const title = (a.innerText || a.textContent || '').trim();
            if (!title) return;
            let snippet = (snippetNode?.innerText || snippetNode?.textContent || '').trim();
            if (!snippet && box) {
              const text = (box.innerText || '').split('\n').map(x => x.trim()).filter(Boolean);
              snippet = text.filter(x => x !== title).slice(0, 5).join(' ');
            }
            rows.push({ title, url: a.href || '', snippet: snippet.slice(0, 900) });
          };
          if (engine === 'bing') {
            for (const item of [...document.querySelectorAll('li.b_algo')]) {
              push(item.querySelector('h2 a'), item, item.querySelector('.b_caption p'));
              if (rows.length >= 40) break;
            }
          } else if (engine === 'duckduckgo') {
            for (const item of [...document.querySelectorAll('.result')]) {
              push(item.querySelector('a.result__a'), item, item.querySelector('.result__snippet'));
              if (rows.length >= 40) break;
            }
          } else {
            for (const a of [...document.querySelectorAll('a[href]')]) {
              const h3 = a.querySelector('h3');
              if (!h3) continue;
              const box = a.closest('div.MjjYud') || a.closest('div[data-snhf]') || a.parentElement?.parentElement;
              const title = (h3.innerText || h3.textContent || '').trim();
              const text = (box?.innerText || '').split('\n').map(x => x.trim()).filter(Boolean);
              rows.push({ title, url: a.href || '', snippet: text.filter(x => x !== title).slice(0, 5).join(' ').slice(0, 900) });
              if (rows.length >= 40) break;
            }
          }
          return { challenge, rows };
        }""",
        engine,
    )


async def _new_context(runtime):
    browser = runtime._browsers["chromium"]
    return await browser.new_context(
        proxy={"server": _proxy_server()},
        viewport={"width": 1180, "height": 820},
        locale="en-US",
        java_script_enabled=True,
        accept_downloads=False,
        service_workers="block",
    )


async def _search_engine_async(runtime, engine: str, query: str, limit: int) -> dict:
    context = await _new_context(runtime)
    page = await context.new_page()
    await page.route("**/*", runtime._route)
    started = perf_counter()
    stage = "goto"
    try:
        response = await page.goto(_engine_url(engine, query), wait_until="domcontentloaded", timeout=TOR_TIMEOUT_MS)
        status = response.status if response else None
        if status == 429:
            return {"engine": engine, "provider_status": "rate_limited", "results": [], "http_status": 429, "latency_ms": int((perf_counter() - started) * 1000)}
        stage = "settle"
        await page.wait_for_timeout(250)
        stage = "extract"
        snapshot = await _extract_serp(page, engine)
        challenged = bool(snapshot.get("challenge"))
        rows = normalize_serp_rows(snapshot.get("rows"), limit)
        for row in rows:
            row["transport"] = "tor"
            row["onion_service"] = is_v3_onion_host(urlsplit(row.get("url") or "").hostname or "")
        return {
            "engine": engine,
            "provider_status": "challenge" if challenged else "complete" if rows else "empty",
            "results": [] if challenged else rows,
            "http_status": status,
            "captcha": challenged,
            "latency_ms": int((perf_counter() - started) * 1000),
        }
    except Exception as error:
        return {
            "engine": engine,
            "provider_status": "error",
            "results": [],
            "error_stage": stage,
            "error_code": classify_browser_error(error),
            "error_type": type(error).__name__,
            "latency_ms": int((perf_counter() - started) * 1000),
        }
    finally:
        await context.close()


async def tor_search_async(runtime, query: str, limit: int, *, engine_searcher=None) -> dict:
    searcher = engine_searcher or _search_engine_async
    async with runtime._semaphores["search"]:
        attempts = []
        started = perf_counter()
        for engine in TOR_SEARCH_ENGINES:
            result = await searcher(runtime, engine, query, limit)
            attempts.append(result)
            if result.get("provider_status") == "complete" and result.get("results"):
                return {
                    "provider": "browser_eye_tor_web",
                    "provider_status": "complete",
                    "transport": "tor",
                    "engine": engine,
                    "results": result.get("results") or [],
                    "attempts": [
                        {
                            "engine": row.get("engine"),
                            "provider_status": row.get("provider_status"),
                            "result_count": len(row.get("results") or []),
                            "error_code": row.get("error_code"),
                            "latency_ms": row.get("latency_ms"),
                        }
                        for row in attempts
                    ],
                    "latency_ms": int((perf_counter() - started) * 1000),
                    "truth_note": "Tor search results are retrieval evidence, not verified opportunity or financial facts.",
                }
        statuses = [row.get("provider_status") for row in attempts]
        status = "challenge" if statuses and all(item in {"challenge", "rate_limited"} for item in statuses) else "empty" if "empty" in statuses else "error"
        return {
            "provider": "browser_eye_tor_web",
            "provider_status": status,
            "transport": "tor",
            "engine": None,
            "results": [],
            "attempts": [
                {"engine": row.get("engine"), "provider_status": row.get("provider_status"), "result_count": len(row.get("results") or []), "error_code": row.get("error_code"), "latency_ms": row.get("latency_ms")}
                for row in attempts
            ],
            "latency_ms": int((perf_counter() - started) * 1000),
        }


async def tor_fetch_async(runtime, url: str) -> dict:
    target = safe_tor_url(url)
    if not target:
        raise ValueError("invalid Tor target URL")
    context = await _new_context(runtime)
    page = await context.new_page()
    await page.route("**/*", runtime._route)
    started = perf_counter()
    try:
        response = await page.goto(target, wait_until="domcontentloaded", timeout=TOR_TIMEOUT_MS)
        await page.wait_for_timeout(250)
        headers = await response.all_headers() if response else {}
        snapshot = await page.evaluate("""() => ({
          title: document.title || '',
          final_url: location.href,
          canonical: document.querySelector('link[rel="canonical"]')?.href || '',
          body_text: (document.body?.innerText || '').slice(0, 50000),
          links: [...document.querySelectorAll('a[href]')].slice(0, 80).map(a => ({
            url: a.href || '', title: (a.innerText || a.textContent || '').trim().slice(0, 240)
          }))
        })""")
        final_url = _clean(snapshot.get("final_url"), MAX_URL)
        host = (urlsplit(final_url).hostname or "").lower() if final_url else ""
        onion_location = safe_tor_url(headers.get("onion-location") or "")
        body_text = str(snapshot.get("body_text") or "")[:50000]
        return {
            "provider": "browser_eye_tor_fetch",
            "provider_status": "complete",
            "transport": "tor",
            "requested_url": target,
            "final_url": final_url,
            "host": host,
            "onion_service": is_v3_onion_host(host),
            "http_status": response.status if response else None,
            "title": _clean(snapshot.get("title"), 300),
            "canonical": _clean(snapshot.get("canonical"), MAX_URL),
            "description": _clean(body_text, 1200),
            "body_text": body_text,
            "links": [row for row in snapshot.get("links", []) if isinstance(row, dict)][:80],
            "onion_location": onion_location or None,
            "latency_ms": int((perf_counter() - started) * 1000),
            "verification": {"verified": False, "state": "tor_retrieval_evidence"},
        }
    except Exception as error:
        return {
            "provider": "browser_eye_tor_fetch",
            "provider_status": "error",
            "transport": "tor",
            "requested_url": target,
            "error_code": classify_browser_error(error),
            "error_type": type(error).__name__,
            "latency_ms": int((perf_counter() - started) * 1000),
            "verification": {"verified": False, "state": "tor_retrieval_failed"},
        }
    finally:
        await context.close()


def install_browser_tor_routes(app, runtime):
    if getattr(app, "_namemachine_tor_routes_installed", False):
        return
    app._namemachine_tor_routes_installed = True

    @app.post("/v1/tor-web-search")
    def tor_web_search():
        if not _authorized():
            return jsonify({"error": "unauthorized"}), 401
        if not _enabled():
            return jsonify({"provider": "browser_eye_tor_web", "provider_status": "disabled", "transport": "tor", "results": []}), 503
        payload = request.get_json(silent=True)
        payload = payload if isinstance(payload, dict) else {}
        query = _clean(payload.get("query"), MAX_QUERY)
        if len(query) < 2:
            return jsonify({"error": "invalid query"}), 400
        try:
            limit = max(1, min(int(payload.get("limit") or MAX_RESULTS), MAX_RESULTS))
        except (TypeError, ValueError):
            limit = MAX_RESULTS
        try:
            runtime._ensure_started()
            future = asyncio.run_coroutine_threadsafe(tor_search_async(runtime, query, limit), runtime._loop)
            return jsonify(future.result(timeout=32.0))
        except Exception as error:
            return jsonify({"provider": "browser_eye_tor_web", "provider_status": "unavailable", "transport": "tor", "results": [], "error_type": type(error).__name__}), 503

    @app.post("/v1/tor-fetch")
    def tor_fetch():
        if not _authorized():
            return jsonify({"error": "unauthorized"}), 401
        if not _enabled():
            return jsonify({"provider": "browser_eye_tor_fetch", "provider_status": "disabled", "transport": "tor"}), 503
        payload = request.get_json(silent=True)
        payload = payload if isinstance(payload, dict) else {}
        target = safe_tor_url(payload.get("url"))
        if not target:
            return jsonify({"error": "invalid Tor target URL"}), 400
        try:
            runtime._ensure_started()
            future = asyncio.run_coroutine_threadsafe(tor_fetch_async(runtime, target), runtime._loop)
            return jsonify(future.result(timeout=18.0))
        except Exception as error:
            return jsonify({"provider": "browser_eye_tor_fetch", "provider_status": "unavailable", "transport": "tor", "error_type": type(error).__name__}), 503


__all__ = [
    "TOR_SEARCH_ENGINES",
    "TOR_TRANSPORT_VERSION",
    "install_browser_tor_routes",
    "is_v3_onion_host",
    "safe_tor_url",
    "tor_diagnostics",
    "tor_fetch_async",
    "tor_search_async",
    "tor_socket_ready",
    "wait_for_tor_socket",
]
