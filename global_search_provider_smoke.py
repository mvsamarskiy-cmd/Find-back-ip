"""One-shot, opt-in production smoke for the private global-search provider.

The probe is disabled by default and deliberately emits only sanitized transport
metadata. It never logs URLs, tokens, response bodies, result URLs, or titles.
"""
from __future__ import annotations

import json
import os
from threading import Thread
from time import sleep

import requests


SMOKE_FLAG = "GLOBAL_SEARCH_STARTUP_SMOKE"
SMOKE_MARKER = "GLOBAL_SEARCH_PROVIDER_SMOKE"


def _enabled() -> bool:
    return str(os.environ.get(SMOKE_FLAG) or "").strip().lower() in {"1", "true", "yes", "on"}


def run_provider_smoke(*, poster=requests.post) -> dict:
    """Run one Browser Eye search and return only non-sensitive diagnostics."""
    base_url = str(os.environ.get("BROWSER_EYE_URL") or "").strip().rstrip("/")
    token = str(os.environ.get("GLOBAL_SEARCH_BROWSER_TOKEN") or "").strip()
    if not base_url or not token:
        return {
            "configured": False,
            "http_status": None,
            "provider_status": "unconfigured",
            "result_count": 0,
            "captcha": False,
            "latency_ms": None,
            "error_type": None,
        }

    try:
        response = poster(
            base_url + "/v1/web-search",
            json={"query": "AI grants Poland EU", "limit": 3},
            headers={
                "Content-Type": "application/json",
                "User-Agent": "NameMachine-provider-smoke/1",
                "X-Global-Search-Token": token,
            },
            timeout=16,
        )
        try:
            payload = response.json() if response.content else {}
        except (TypeError, ValueError):
            payload = {}
        rows = payload.get("results") if isinstance(payload, dict) else []
        rows = rows if isinstance(rows, list) else []
        return {
            "configured": True,
            "http_status": int(response.status_code),
            "provider_status": str(payload.get("provider_status") or "unknown")[:80] if isinstance(payload, dict) else "unknown",
            "result_count": len(rows),
            "captcha": bool(payload.get("captcha", False)) if isinstance(payload, dict) else False,
            "latency_ms": payload.get("latency_ms") if isinstance(payload, dict) else None,
            "error_type": str(payload.get("error_type") or "")[:80] or None if isinstance(payload, dict) else None,
        }
    except requests.RequestException as error:
        return {
            "configured": True,
            "http_status": None,
            "provider_status": "network_error",
            "result_count": 0,
            "captcha": False,
            "latency_ms": None,
            "error_type": type(error).__name__,
        }
    except Exception as error:
        return {
            "configured": True,
            "http_status": None,
            "provider_status": "error",
            "result_count": 0,
            "captcha": False,
            "latency_ms": None,
            "error_type": type(error).__name__,
        }


def _background_probe():
    # Give Gunicorn enough time to finish binding before doing external work.
    sleep(1.0)
    result = run_provider_smoke()
    print(f"{SMOKE_MARKER} {json.dumps(result, ensure_ascii=True, separators=(',', ':'))}", flush=True)


def maybe_start_provider_smoke() -> bool:
    if not _enabled():
        return False
    Thread(target=_background_probe, name="global-search-provider-smoke", daemon=True).start()
    return True


__all__ = ["SMOKE_FLAG", "SMOKE_MARKER", "maybe_start_provider_smoke", "run_provider_smoke"]
