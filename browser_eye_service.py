"""Private dual-engine Browser Intelligence service for NameMachine.

The service is intentionally separate from the web/search worker. Playwright keeps
one Chromium and one WebKit process warm, opens isolated short-lived contexts,
blocks heavyweight assets, reads rendered DOM/meta/script data plus compact XHR
JSON, and returns a small ProfileFingerprint. Screenshots are not part of the hot
path.

Absence is evidence of public absence only. This service never emits `claimable`.
Google is used only as a sparse indexed-web collision sensor and never decides
availability by itself.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import os
import re
from threading import Event, Lock, Thread
from time import monotonic, perf_counter
from urllib.parse import quote_plus, urlsplit

from flask import Flask, jsonify, request


app = Flask(__name__)

PROFILE_URLS = {
    "instagram": "https://www.instagram.com/{handle}/",
    "telegram": "https://t.me/{handle}",
    "tiktok": "https://www.tiktok.com/@{handle}",
    "youtube": "https://www.youtube.com/@{handle}",
    "facebook": "https://www.facebook.com/{handle}",
    "x": "https://x.com/{handle}",
}

MISSING_MARKERS = {
    "instagram": ("sorry, this page isn't available", "page isn't available"),
    "telegram": ("username not found", "page not found"),
    "tiktok": ("couldn't find this account", "couldn’t find this account", "account not found"),
    "youtube": ("this page isn't available", "404 not found"),
    "facebook": ("this content isn't available", "page isn't available", "this page isn't available"),
    "x": ("this account doesn’t exist", "this account doesn't exist", "account doesn’t exist"),
}

CHALLENGE_MARKERS = (
    "captcha", "verify you are human", "unusual traffic", "challenge_required",
    "checkpoint", "security check", "robot check", "access denied",
)
LOGIN_MARKERS = (
    "log in to continue", "login to continue", "sign in to continue",
    "log into instagram", "join x today", "create an account or log in",
)


def _bounded_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


PROFILE_TIMEOUT_MS = _bounded_int("BROWSER_PROFILE_TIMEOUT_MS", 3500, 1200, 12000)
HYDRATION_WAIT_MS = _bounded_int("BROWSER_HYDRATION_WAIT_MS", 350, 50, 1500)
CHROMIUM_CONCURRENCY = _bounded_int("BROWSER_CHROMIUM_CONCURRENCY", 4, 1, 12)
WEBKIT_CONCURRENCY = _bounded_int("BROWSER_WEBKIT_CONCURRENCY", 2, 1, 8)
SEARCH_CONCURRENCY = _bounded_int("BROWSER_SEARCH_CONCURRENCY", 1, 1, 3)
POSITIVE_CACHE_SECONDS = _bounded_int("BROWSER_POSITIVE_CACHE_SECONDS", 120, 0, 600)
ABSENCE_CACHE_SECONDS = _bounded_int("BROWSER_ABSENCE_CACHE_SECONDS", 45, 0, 180)


def _clean_handle(value):
    return re.sub(r"[^A-Za-z0-9_.-]", "", str(value or "").strip().lstrip("@"))[:64].lower()


def _safe_text(value, limit=400):
    return " ".join(str(value or "").split())[:limit]


def _canonical_matches(platform, handle, canonical):
    try:
        parsed = urlsplit(str(canonical or ""))
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    expected = {
        "instagram": ("instagram.com", f"/{handle}"),
        "telegram": ("t.me", f"/{handle}"),
        "tiktok": ("tiktok.com", f"/@{handle}"),
        "youtube": ("youtube.com", f"/@{handle}"),
        "facebook": ("facebook.com", f"/{handle}"),
        "x": ("x.com", f"/{handle}"),
    }.get(platform)
    if not expected:
        return False
    expected_host, expected_path = expected
    return (host == expected_host or host.endswith("." + expected_host)) and path == expected_path


def _structured_identity_match(platform, handle, text):
    haystack = str(text or "").lower()
    escaped = re.escape(handle.lower())
    patterns = [
        rf'"username"\s*:\s*"{escaped}"',
        rf'"uniqueid"\s*:\s*"{escaped}"',
        rf'"screen_name"\s*:\s*"{escaped}"',
        rf'"vanity"\s*:\s*"{escaped}"',
        rf'"handle"\s*:\s*"@?{escaped}"',
        rf'/@{escaped}(?:["/?#]|$)',
    ]
    if platform == "telegram":
        patterns.append(rf'"username"\s*:\s*"{escaped}"')
    return any(re.search(pattern, haystack, flags=re.I) for pattern in patterns)


def _profile_id(text):
    haystack = str(text or "")[:300000]
    patterns = (
        r'"(?:user_?id|profile_?id|channel_?id|channelId)"\s*:\s*"?([A-Za-z0-9_-]{4,64})',
        r'"id"\s*:\s*"([0-9]{5,32})"',
    )
    for pattern in patterns:
        match = re.search(pattern, haystack, flags=re.I)
        if match:
            return match.group(1)[:64]
    return ""


def _display_name(og_title, title, handle):
    source = _safe_text(og_title or title, 180)
    if not source:
        return ""
    value = re.sub(rf"\s*\(@?{re.escape(handle)}\).*", "", source, flags=re.I)
    value = re.sub(rf"\s*[-|•·]\s*@?{re.escape(handle)}.*", "", value, flags=re.I)
    for suffix in (" • Instagram photos and videos", " | TikTok", " - YouTube"):
        value = value.replace(suffix, "")
    return _safe_text(value, 120)


def fingerprint_from_snapshot(platform, handle, snapshot, network_rows=None, *, engine="chromium", latency_ms=None, http_status=None):
    """Pure parser used by production Playwright and normal unit tests."""
    platform = str(platform or "").lower()
    handle = _clean_handle(handle)
    snap = dict(snapshot or {}) if isinstance(snapshot, dict) else {}
    network_rows = list(network_rows or [])
    title = _safe_text(snap.get("title"), 240)
    canonical = _safe_text(snap.get("canonical"), 600)
    og_title = _safe_text(snap.get("og_title"), 240)
    og_image = _safe_text(snap.get("og_image"), 1200)
    og_description = _safe_text(snap.get("og_description"), 600)
    body = str(snap.get("body_text") or "")[:80000]
    scripts = str(snap.get("script_text") or "")[:240000]
    # Keep JSON response bodies raw instead of JSON-encoding the containing
    # Python rows. Encoding would escape quotes (\"username\") and make exact
    # identity parsers miss data the browser actually observed on XHR/fetch.
    network_text = "\n".join(
        str(row.get("body") or "")
        for row in network_rows
        if isinstance(row, dict)
    )[:240000]
    combined = "\n".join((title, canonical, og_title, og_description, body, scripts, network_text))
    lower = combined.lower()

    challenge = any(marker in lower for marker in CHALLENGE_MARKERS)
    login_wall = any(marker in lower for marker in LOGIN_MARKERS)
    missing = any(marker in lower for marker in MISSING_MARKERS.get(platform, ()))
    canonical_match = _canonical_matches(platform, handle, canonical)
    structured_match = _structured_identity_match(platform, handle, scripts + "\n" + network_text)
    meta_match = f"@{handle}" in (title + " " + og_title).lower()
    avatar_url = og_image or _safe_text(snap.get("avatar_url"), 1200)
    avatar_present = bool(avatar_url and not avatar_url.startswith("data:"))
    profile_id = _profile_id(scripts + "\n" + network_text)
    network_identity = _structured_identity_match(platform, handle, network_text)

    if challenge:
        signal = "unknown"
        confidence = 0.0
        detail = "Browser reached an anti-bot/challenge page"
    elif (structured_match or network_identity or canonical_match or (meta_match and avatar_present)) and not missing:
        signal = "exists"
        confidence = 0.97 if network_identity or structured_match else 0.93 if canonical_match else 0.9
        detail = "Rendered page contains an exact profile identity fingerprint"
    elif missing and not (structured_match or canonical_match or network_identity):
        signal = "absent"
        confidence = 0.9
        detail = "Rendered page contains an explicit platform-specific missing-profile marker"
    else:
        signal = "unknown"
        confidence = 0.0
        detail = "Rendered page is inconclusive"

    return {
        "signal": signal,
        "confidence": confidence,
        "engine": engine,
        "latency_ms": latency_ms,
        "http_status": http_status,
        "final_url": _safe_text(snap.get("final_url"), 1200),
        "username": handle if signal == "exists" else "",
        "username_exact": signal == "exists",
        "display_name": _display_name(og_title, title, handle) if signal == "exists" else "",
        "profile_id": profile_id if signal == "exists" else "",
        "avatar_present": avatar_present if signal == "exists" else False,
        "avatar_url": avatar_url if signal == "exists" else "",
        "bio_present": bool(og_description) if signal == "exists" else False,
        "canonical_url": canonical,
        "canonical_match": canonical_match,
        "login_wall": login_wall,
        "challenge": challenge,
        "rate_limited": http_status == 429,
        "network_identity": network_identity,
        "detail": detail,
        "claimability": "unconfirmed",
        "authoritative_claimability": False,
    }


def search_fingerprint(query, handle, platform, snapshot, *, latency_ms=None):
    """Reduce a rendered Google SERP to collision-only evidence."""
    snap = dict(snapshot or {}) if isinstance(snapshot, dict) else {}
    body = str(snap.get("body_text") or "").lower()
    challenge = any(marker in body for marker in ("unusual traffic", "captcha", "verify you are human"))
    expected_host = {
        "instagram": "instagram.com", "telegram": "t.me", "tiktok": "tiktok.com",
        "youtube": "youtube.com", "facebook": "facebook.com", "x": "x.com",
    }.get(str(platform or "").lower(), "")
    clean = _clean_handle(handle)
    hits = []
    for raw in snap.get("links", []) if isinstance(snap.get("links"), list) else []:
        if not isinstance(raw, dict):
            continue
        href = _safe_text(raw.get("href"), 1400)
        text = _safe_text(raw.get("text"), 300)
        try:
            parsed = urlsplit(href)
        except ValueError:
            continue
        host = (parsed.hostname or "").lower()
        path = parsed.path.lower()
        if expected_host and (host == expected_host or host.endswith("." + expected_host)):
            if f"/{clean}" in path or f"/@{clean}" in path:
                hits.append({"url": href, "title": text})
        if len(hits) >= 5:
            break
    return {
        "query": _safe_text(query, 500),
        "exact_profile_hits": len(hits),
        "hits": hits,
        "captcha": challenge,
        "latency_ms": latency_ms,
        "role": "indexed_collision_corroboration",
        "can_confirm_claimability": False,
        "can_confirm_occupancy": False,
    }


class BrowserRuntime:
    def __init__(self):
        self._loop = None
        self._thread = None
        self._ready = Event()
        self._start_lock = Lock()
        self._startup_error = None
        self._playwright = None
        self._browsers = {}
        self._semaphores = {}
        self._cache = {}
        self._cache_lock = Lock()

    def _ensure_started(self):
        if self._thread and self._thread.is_alive() and self._ready.is_set():
            if self._startup_error:
                raise RuntimeError(self._startup_error)
            return
        with self._start_lock:
            if self._thread and self._thread.is_alive():
                pass
            else:
                self._ready.clear()
                self._startup_error = None
                self._thread = Thread(target=self._thread_main, name="browser-eye-loop", daemon=True)
                self._thread.start()
        if not self._ready.wait(timeout=25):
            raise RuntimeError("Browser Eye startup timed out")
        if self._startup_error:
            raise RuntimeError(self._startup_error)

    def _thread_main(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._boot())
        except Exception as error:
            self._startup_error = f"{type(error).__name__}: {error}"
            self._ready.set()
            return
        self._ready.set()
        loop.run_forever()

    async def _boot(self):
        # Playwright is a browser-service-only dependency. Importing this module in
        # the main app/test suite therefore stays lightweight.
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browsers = {
            "chromium": await self._playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"]),
            "webkit": await self._playwright.webkit.launch(headless=True),
        }
        self._semaphores = {
            "chromium": asyncio.Semaphore(CHROMIUM_CONCURRENCY),
            "webkit": asyncio.Semaphore(WEBKIT_CONCURRENCY),
            "search": asyncio.Semaphore(SEARCH_CONCURRENCY),
        }

    def _cache_key(self, kind, engine, platform, value):
        return (kind, engine, platform, str(value).strip().lower())

    def _cache_get(self, key):
        now = monotonic()
        with self._cache_lock:
            cached = self._cache.get(key)
            if not cached:
                return None
            expires, value = cached
            if expires <= now:
                self._cache.pop(key, None)
                return None
            result = deepcopy(value)
        result["cache_hit"] = True
        return result

    def _cache_put(self, key, value):
        if not isinstance(value, dict):
            return
        signal = str(value.get("signal") or "")
        ttl = POSITIVE_CACHE_SECONDS if signal == "exists" else ABSENCE_CACHE_SECONDS if signal == "absent" else 0
        if ttl <= 0:
            return
        with self._cache_lock:
            self._cache[key] = (monotonic() + ttl, deepcopy(value))

    @staticmethod
    async def _route(route):
        resource_type = route.request.resource_type
        if resource_type in {"image", "media", "font"}:
            await route.abort()
        else:
            await route.continue_()

    async def _profile_async(self, platform, handle, engine):
        async with self._semaphores[engine]:
            browser = self._browsers[engine]
            context = await browser.new_context(
                viewport={"width": 1100, "height": 760},
                locale="en-US",
                java_script_enabled=True,
            )
            page = await context.new_page()
            await page.route("**/*", self._route)
            network_rows = []

            async def capture(response):
                if len(network_rows) >= 12:
                    return
                if response.request.resource_type not in {"xhr", "fetch"}:
                    return
                content_type = str((await response.all_headers()).get("content-type") or "").lower()
                if "json" not in content_type:
                    return
                try:
                    text = await response.text()
                except Exception:
                    return
                if len(text) > 50000:
                    text = text[:50000]
                network_rows.append({"url": response.url[:1000], "status": response.status, "body": text})

            page.on("response", lambda response: asyncio.create_task(capture(response)))
            url = PROFILE_URLS[platform].format(handle=handle)
            started = perf_counter()
            response = None
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=PROFILE_TIMEOUT_MS)
                await page.wait_for_timeout(HYDRATION_WAIT_MS)
                snapshot = await page.evaluate("""() => {
                    const pick = (selector, attr='content') => document.querySelector(selector)?.getAttribute(attr) || '';
                    const scripts = [...document.scripts].map(s => s.textContent || '').join('\n').slice(0, 240000);
                    const avatar = [...document.images].map(i => i.currentSrc || i.src || '').find(Boolean) || '';
                    return {
                      title: document.title || '',
                      final_url: location.href,
                      canonical: document.querySelector('link[rel="canonical"]')?.href || '',
                      og_title: pick('meta[property="og:title"]'),
                      og_image: pick('meta[property="og:image"]'),
                      og_description: pick('meta[property="og:description"]'),
                      body_text: (document.body?.innerText || '').slice(0, 80000),
                      script_text: scripts,
                      avatar_url: avatar,
                    };
                }""")
                latency = int((perf_counter() - started) * 1000)
                status = response.status if response else None
                if status == 429:
                    return {
                        "signal": "rate_limited", "confidence": 0.0, "engine": engine,
                        "latency_ms": latency, "http_status": 429, "claimability": "unconfirmed",
                    }
                return fingerprint_from_snapshot(
                    platform,
                    handle,
                    snapshot,
                    network_rows,
                    engine=engine,
                    latency_ms=latency,
                    http_status=status,
                )
            except Exception as error:
                return {
                    "signal": "unknown",
                    "confidence": 0.0,
                    "engine": engine,
                    "latency_ms": int((perf_counter() - started) * 1000),
                    "detail": f"Browser probe failed: {type(error).__name__}",
                    "claimability": "unconfirmed",
                    "authoritative_claimability": False,
                }
            finally:
                await context.close()

    async def _search_async(self, query, handle, platform):
        async with self._semaphores["search"]:
            browser = self._browsers["chromium"]
            context = await browser.new_context(viewport={"width": 1100, "height": 760}, locale="en-US")
            page = await context.new_page()
            await page.route("**/*", self._route)
            started = perf_counter()
            try:
                await page.goto(
                    "https://www.google.com/search?q=" + quote_plus(query) + "&num=10&hl=en",
                    wait_until="domcontentloaded",
                    timeout=PROFILE_TIMEOUT_MS,
                )
                await page.wait_for_timeout(min(HYDRATION_WAIT_MS, 300))
                snapshot = await page.evaluate("""() => ({
                  body_text: (document.body?.innerText || '').slice(0, 80000),
                  links: [...document.querySelectorAll('a[href]')].slice(0, 120).map(a => ({
                    href: a.href || '', text: (a.innerText || a.textContent || '').trim().slice(0, 300)
                  }))
                })""")
                return search_fingerprint(
                    query,
                    handle,
                    platform,
                    snapshot,
                    latency_ms=int((perf_counter() - started) * 1000),
                )
            except Exception as error:
                return {
                    "query": _safe_text(query, 500),
                    "exact_profile_hits": 0,
                    "hits": [],
                    "captcha": False,
                    "error": type(error).__name__,
                    "latency_ms": int((perf_counter() - started) * 1000),
                    "role": "indexed_collision_corroboration",
                    "can_confirm_claimability": False,
                    "can_confirm_occupancy": False,
                }
            finally:
                await context.close()

    def profile(self, platform, handle, engine):
        self._ensure_started()
        key = self._cache_key("profile", engine, platform, handle)
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        future = asyncio.run_coroutine_threadsafe(self._profile_async(platform, handle, engine), self._loop)
        value = future.result(timeout=max(8.0, PROFILE_TIMEOUT_MS / 1000 + 4.0))
        self._cache_put(key, value)
        return value

    def search(self, query, handle, platform):
        self._ensure_started()
        future = asyncio.run_coroutine_threadsafe(self._search_async(query, handle, platform), self._loop)
        return future.result(timeout=max(8.0, PROFILE_TIMEOUT_MS / 1000 + 4.0))

    def diagnostics(self):
        return {
            "started": bool(self._thread and self._thread.is_alive() and self._ready.is_set() and not self._startup_error),
            "startup_error": self._startup_error,
            "engines": ["chromium", "webkit"],
            "screenshots_hot_path": False,
            "network_json_capture": True,
            "heavy_assets_blocked": ["image", "media", "font"],
            "profile_timeout_ms": PROFILE_TIMEOUT_MS,
            "hydration_wait_ms": HYDRATION_WAIT_MS,
        }


RUNTIME = BrowserRuntime()


def _authorized():
    expected = str(os.environ.get("BROWSER_EYE_TOKEN") or "").strip()
    if not expected:
        return True
    supplied = str(request.headers.get("X-Browser-Eye-Token") or "")
    return supplied == expected


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "browser-eye", **RUNTIME.diagnostics()})


@app.post("/v1/profile")
def profile():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    platform = str(data.get("platform") or "").lower()
    engine = str(data.get("engine") or "chromium").lower()
    handle = _clean_handle(data.get("handle"))
    if platform not in PROFILE_URLS or engine not in {"chromium", "webkit"} or not handle:
        return jsonify({"error": "invalid profile probe"}), 400
    try:
        return jsonify(RUNTIME.profile(platform, handle, engine))
    except Exception as error:
        return jsonify({
            "signal": "unknown", "confidence": 0.0, "engine": engine,
            "detail": f"Browser service unavailable: {type(error).__name__}",
            "claimability": "unconfirmed",
        }), 503


@app.post("/v1/search")
def search():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    query = _safe_text(data.get("query"), 500)
    handle = _clean_handle(data.get("handle"))
    platform = str(data.get("platform") or "").lower()
    if not query or not handle or platform not in PROFILE_URLS:
        return jsonify({"error": "invalid search probe"}), 400
    try:
        return jsonify(RUNTIME.search(query, handle, platform))
    except Exception as error:
        return jsonify({
            "query": query, "exact_profile_hits": 0, "hits": [], "captcha": False,
            "error": type(error).__name__, "role": "indexed_collision_corroboration",
            "can_confirm_claimability": False, "can_confirm_occupancy": False,
        }), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), threaded=True)
