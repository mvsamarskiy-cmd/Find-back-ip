"""Generic multi-engine web search for the private Browser Eye service.

This is isolated from NameMachine's social-profile Browser Eye auth and semantics.
It discovers public web results only; it never claims eligibility, availability,
award status, legal status, or truth beyond what the observed source/search page says.

Search engines are deliberately redundant: a Google navigation failure, anti-bot
challenge, or empty SERP falls through to Bing and then DuckDuckGo instead of
turning the entire private Global Search into a single-provider failure.
"""
from __future__ import annotations

import asyncio
import hmac
import os
from time import perf_counter
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit

from flask import jsonify, request


MAX_RESULTS = 20
MAX_QUERY = 1800
SEARCH_ENGINES = ("google", "bing", "duckduckgo")
ENGINE_TIMEOUT_MS = 3500


def _clean(value, limit=1200):
    return " ".join(str(value or "").split())[:limit]


def _external_url(raw):
    value = _clean(raw, 1800)
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    query = parse_qs(parsed.query)

    if host.endswith("google.com") and parsed.path == "/url":
        target = (query.get("q") or query.get("url") or [""])[0]
        return _external_url(target)
    if host.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = (query.get("uddg") or [""])[0]
        return _external_url(unquote(target))

    if parsed.scheme not in {"http", "https"} or not host:
        return ""
    if (
        host.endswith("google.com")
        or host.endswith("googleusercontent.com")
        or host.endswith("bing.com")
        or host.endswith("duckduckgo.com")
    ):
        return ""
    return value


def normalize_serp_rows(rows, limit=MAX_RESULTS):
    """Normalize rendered search rows without inventing fields not observed."""
    output = []
    seen = set()
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        url = _external_url(raw.get("url"))
        title = _clean(raw.get("title"), 300)
        snippet = _clean(raw.get("snippet"), 900)
        if not url or not title:
            continue
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        key = f"{(parsed.hostname or '').lower()}{parsed.path.rstrip('/')}"
        if not key or key in seen:
            continue
        seen.add(key)
        output.append({
            "title": title,
            "url": url,
            "host": (parsed.hostname or "").lower().removeprefix("www."),
            "description": snippet,
        })
        if len(output) >= max(1, min(int(limit or MAX_RESULTS), MAX_RESULTS)):
            break
    return output


def _authorized():
    expected = str(os.environ.get("GLOBAL_SEARCH_BROWSER_TOKEN") or "").strip()
    supplied = str(request.headers.get("X-Global-Search-Token") or "").strip()
    return bool(expected and supplied) and hmac.compare_digest(supplied, expected)


def classify_browser_error(error):
    """Return a bounded non-sensitive failure code, never the raw Playwright text."""
    message = str(error or "").casefold()
    patterns = (
        ("err_name_not_resolved", "dns_error"),
        ("err_connection_refused", "connection_refused"),
        ("err_connection_reset", "connection_reset"),
        ("err_timed_out", "network_timeout"),
        ("timeout", "timeout"),
        ("err_failed", "navigation_failed"),
        ("err_http2_protocol_error", "http2_error"),
        ("err_cert", "certificate_error"),
        ("target page, context or browser has been closed", "target_closed"),
        ("browser has been closed", "browser_closed"),
    )
    for needle, code in patterns:
        if needle in message:
            return code
    name = type(error).__name__ if error is not None else "Error"
    return _clean(name, 64).lower() or "error"


def _engine_url(engine, query):
    encoded = quote_plus(query)
    if engine == "bing":
        return f"https://www.bing.com/search?q={encoded}&count=20&setlang=en"
    if engine == "duckduckgo":
        return f"https://html.duckduckgo.com/html/?q={encoded}"
    return f"https://www.google.com/search?q={encoded}&num=20&hl=en"


async def _extract_snapshot(page, engine):
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
              const text = (box.innerText || '').split('\\n').map(x => x.trim()).filter(Boolean);
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
              const text = (box?.innerText || '').split('\\n').map(x => x.trim()).filter(Boolean);
              const snippet = text.filter(x => x !== title).slice(0, 5).join(' ').slice(0, 900);
              rows.push({ title, url: a.href || '', snippet });
              if (rows.length >= 40) break;
            }
          }
          return { challenge, rows };
        }""",
        engine,
    )


async def _search_engine_async(runtime, engine, query, limit):
    browser = runtime._browsers["chromium"]
    context = await browser.new_context(
        viewport={"width": 1180, "height": 820},
        locale="en-US",
        java_script_enabled=True,
    )
    page = await context.new_page()
    await page.route("**/*", runtime._route)
    started = perf_counter()
    stage = "goto"
    try:
        response = await page.goto(
            _engine_url(engine, query),
            wait_until="domcontentloaded",
            timeout=ENGINE_TIMEOUT_MS,
        )
        http_status = response.status if response else None
        if http_status == 429:
            return {
                "engine": engine,
                "provider_status": "rate_limited",
                "results": [],
                "captcha": False,
                "http_status": 429,
                "latency_ms": int((perf_counter() - started) * 1000),
            }
        stage = "settle"
        await page.wait_for_timeout(180)
        stage = "extract"
        snapshot = await _extract_snapshot(page, engine)
        rows = normalize_serp_rows(snapshot.get("rows"), limit)
        challenged = bool(snapshot.get("challenge"))
        return {
            "engine": engine,
            "provider_status": "challenge" if challenged else "complete" if rows else "empty",
            "results": [] if challenged else rows,
            "captcha": challenged,
            "http_status": http_status,
            "latency_ms": int((perf_counter() - started) * 1000),
        }
    except Exception as error:
        return {
            "engine": engine,
            "provider_status": "error",
            "results": [],
            "captcha": False,
            "http_status": None,
            "error_stage": stage,
            "error_code": classify_browser_error(error),
            "error_type": type(error).__name__,
            "latency_ms": int((perf_counter() - started) * 1000),
        }
    finally:
        await context.close()


def _compact_attempt(row):
    if not isinstance(row, dict):
        return {"engine": "unknown", "provider_status": "error", "result_count": 0}
    return {
        key: row.get(key)
        for key in (
            "engine", "provider_status", "http_status", "captcha", "latency_ms",
            "error_stage", "error_code", "error_type",
        )
        if row.get(key) is not None
    } | {"result_count": len(row.get("results") or [])}


def _final_status(attempts):
    statuses = [str(row.get("provider_status") or "error") for row in attempts if isinstance(row, dict)]
    if "empty" in statuses or "complete" in statuses:
        return "empty"
    if "rate_limited" in statuses and all(status in {"rate_limited", "challenge"} for status in statuses):
        return "rate_limited"
    if "challenge" in statuses and all(status in {"challenge", "rate_limited"} for status in statuses):
        return "challenge"
    return "error"


async def _search_async(runtime, query, limit, *, engine_searcher=None):
    searcher = engine_searcher or _search_engine_async
    async with runtime._semaphores["search"]:
        attempts = []
        total_started = perf_counter()
        for engine in SEARCH_ENGINES:
            result = await searcher(runtime, engine, query, limit)
            attempts.append(result)
            if result.get("provider_status") == "complete" and result.get("results"):
                return {
                    "provider": "browser_eye_web",
                    "provider_status": "complete",
                    "engine": engine,
                    "results": result.get("results") or [],
                    "captcha": False,
                    "attempts": [_compact_attempt(row) for row in attempts],
                    "latency_ms": int((perf_counter() - total_started) * 1000),
                }
        return {
            "provider": "browser_eye_web",
            "provider_status": _final_status(attempts),
            "engine": None,
            "results": [],
            "captcha": any(bool(row.get("captcha")) for row in attempts if isinstance(row, dict)),
            "attempts": [_compact_attempt(row) for row in attempts],
            "latency_ms": int((perf_counter() - total_started) * 1000),
        }


def install_browser_global_search(app, runtime):
    if getattr(app, "_namemachine_global_browser_search_installed", False):
        return
    app._namemachine_global_browser_search_installed = True

    @app.post("/v1/web-search")
    def web_search():
        if not _authorized():
            return jsonify({"error": "unauthorized"}), 401
        payload = request.get_json(silent=True)
        payload = payload if isinstance(payload, dict) else {}
        query = _clean(payload.get("query"), MAX_QUERY)
        try:
            limit = max(1, min(int(payload.get("limit") or MAX_RESULTS), MAX_RESULTS))
        except (TypeError, ValueError):
            limit = MAX_RESULTS
        if len(query) < 2:
            return jsonify({"error": "invalid query"}), 400
        try:
            runtime._ensure_started()
            future = asyncio.run_coroutine_threadsafe(_search_async(runtime, query, limit), runtime._loop)
            return jsonify(future.result(timeout=14.0))
        except Exception as error:
            return jsonify({
                "provider": "browser_eye_web",
                "provider_status": "unavailable",
                "results": [],
                "error_type": type(error).__name__,
            }), 503


__all__ = [
    "SEARCH_ENGINES", "classify_browser_error", "install_browser_global_search",
    "normalize_serp_rows",
]
