"""Generic Google SERP search for the private Browser Eye service.

This is isolated from NameMachine's social-profile Browser Eye auth and semantics.
It discovers public web results only; it never claims eligibility, availability,
award status, legal status, or truth beyond what the source page/search snippet says.
"""
from __future__ import annotations

import asyncio
import hmac
import os
from time import perf_counter
from urllib.parse import parse_qs, quote_plus, urlsplit

from flask import jsonify, request


MAX_RESULTS = 20
MAX_QUERY = 1800


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
    if host.endswith("google.com") and parsed.path == "/url":
        target = (parse_qs(parsed.query).get("q") or parse_qs(parsed.query).get("url") or [""])[0]
        return _external_url(target)
    if parsed.scheme not in {"http", "https"} or not host:
        return ""
    if host.endswith("google.com") or host.endswith("googleusercontent.com"):
        return ""
    return value


def normalize_serp_rows(rows, limit=MAX_RESULTS):
    """Normalize rendered Google rows without inventing fields not observed."""
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


async def _search_async(runtime, query, limit):
    async with runtime._semaphores["search"]:
        browser = runtime._browsers["chromium"]
        context = await browser.new_context(
            viewport={"width": 1180, "height": 820},
            locale="en-US",
            java_script_enabled=True,
        )
        page = await context.new_page()
        await page.route("**/*", runtime._route)
        started = perf_counter()
        try:
            await page.goto(
                "https://www.google.com/search?q=" + quote_plus(query) + "&num=20&hl=en",
                wait_until="domcontentloaded",
                timeout=3500,
            )
            await page.wait_for_timeout(250)
            snapshot = await page.evaluate("""() => {
              const challenge = /unusual traffic|captcha|verify you are human/i.test(document.body?.innerText || '');
              const rows = [];
              for (const a of [...document.querySelectorAll('a[href]')]) {
                const h3 = a.querySelector('h3');
                if (!h3) continue;
                const box = a.closest('div.MjjYud') || a.closest('div[data-snhf]') || a.parentElement?.parentElement;
                const text = (box?.innerText || '').split('\n').map(x => x.trim()).filter(Boolean);
                const title = (h3.innerText || h3.textContent || '').trim();
                const snippet = text.filter(x => x !== title).slice(0, 5).join(' ').slice(0, 900);
                rows.push({ title, url: a.href || '', snippet });
                if (rows.length >= 40) break;
              }
              return { challenge, rows };
            }""")
            return {
                "provider": "browser_eye_google",
                "provider_status": "challenge" if snapshot.get("challenge") else "complete",
                "results": [] if snapshot.get("challenge") else normalize_serp_rows(snapshot.get("rows"), limit),
                "captcha": bool(snapshot.get("challenge")),
                "latency_ms": int((perf_counter() - started) * 1000),
            }
        except Exception as error:
            return {
                "provider": "browser_eye_google",
                "provider_status": "error",
                "results": [],
                "captcha": False,
                "error_type": type(error).__name__,
                "latency_ms": int((perf_counter() - started) * 1000),
            }
        finally:
            await context.close()


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
                "provider": "browser_eye_google",
                "provider_status": "unavailable",
                "results": [],
                "error_type": type(error).__name__,
            }), 503


__all__ = ["install_browser_global_search", "normalize_serp_rows"]
