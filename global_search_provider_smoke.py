"""One-shot, opt-in production smoke for the private global-search provider.

The probe is disabled by default and deliberately emits only sanitized transport
metadata. It never logs URLs, tokens, response bodies, result URLs, titles, or
user query text.
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


def _safe_text(value, limit=80):
    return " ".join(str(value or "").split())[:limit]


def _safe_attempts(value):
    output = []
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        row = {}
        for key in ("engine", "provider_status", "error_stage", "error_code", "error_type"):
            if raw.get(key) is not None:
                row[key] = _safe_text(raw.get(key), 80)
        for key in ("http_status", "result_count", "latency_ms"):
            if raw.get(key) is not None:
                try:
                    row[key] = int(raw.get(key))
                except (TypeError, ValueError):
                    pass
        if raw.get("captcha") is not None:
            row["captcha"] = bool(raw.get("captcha"))
        output.append(row)
        if len(output) >= 3:
            break
    return output


def run_provider_smoke(*, poster=requests.post) -> dict:
    """Run one Browser Eye search and return only non-sensitive diagnostics."""
    base_url = str(os.environ.get("BROWSER_EYE_URL") or "").strip().rstrip("/")
    token = str(os.environ.get("GLOBAL_SEARCH_BROWSER_TOKEN") or "").strip()
    if not base_url or not token:
        return {
            "configured": False,
            "http_status": None,
            "provider_status": "unconfigured",
            "engine": None,
            "result_count": 0,
            "captcha": False,
            "latency_ms": None,
            "error_type": None,
            "attempts": [],
        }

    try:
        response = poster(
            base_url + "/v1/web-search",
            json={"query": "AI grants Poland EU", "limit": 3},
            headers={
                "Content-Type": "application/json",
                "User-Agent": "NameMachine-provider-smoke/2",
                "X-Global-Search-Token": token,
            },
            timeout=16,
        )
        try:
            payload = response.json() if response.content else {}
        except (TypeError, ValueError):
            payload = {}
        payload = payload if isinstance(payload, dict) else {}
        rows = payload.get("results")
        rows = rows if isinstance(rows, list) else []
        return {
            "configured": True,
            "http_status": int(response.status_code),
            "provider_status": _safe_text(payload.get("provider_status") or "unknown"),
            "engine": _safe_text(payload.get("engine"), 40) or None,
            "result_count": len(rows),
            "captcha": bool(payload.get("captcha", False)),
            "latency_ms": payload.get("latency_ms"),
            "error_type": _safe_text(payload.get("error_type")) or None,
            "attempts": _safe_attempts(payload.get("attempts")),
        }
    except requests.RequestException as error:
        return {
            "configured": True,
            "http_status": None,
            "provider_status": "network_error",
            "engine": None,
            "result_count": 0,
            "captcha": False,
            "latency_ms": None,
            "error_type": type(error).__name__,
            "attempts": [],
        }
    except Exception as error:
        return {
            "configured": True,
            "http_status": None,
            "provider_status": "error",
            "engine": None,
            "result_count": 0,
            "captcha": False,
            "latency_ms": None,
            "error_type": type(error).__name__,
            "attempts": [],
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
