"""Readiness wrapper for the private Browser Eye service.

Railway must not mark the service healthy merely because Flask/Gunicorn booted.
The readiness probe warms Playwright and launches both Chromium and WebKit once,
so a missing browser runtime fails deployment instead of failing later on the
first real NameMachine candidate.
"""
from __future__ import annotations

import os

from flask import jsonify

import browser_eye_service as browser_eye_module
from browser_eye_global_search import install_browser_global_search
from browser_eye_hardening import install_browser_eye_hardening
from browser_eye_service import RUNTIME, app


# Harden identity interpretation before the first real or readiness-triggered
# browser task. A requested URL/error shell can no longer count as occupancy.
install_browser_eye_hardening(browser_eye_module)

# Generic global web search is a separate private route/token and does not change
# the conservative social-profile occupancy/claimability semantics above.
install_browser_global_search(app, RUNTIME)


def ready_health():
    try:
        RUNTIME._ensure_started()
    except Exception as error:
        return jsonify({
            "status": "error",
            "service": "browser-eye",
            "ready": False,
            "error_type": type(error).__name__,
        }), 503
    return jsonify({
        "status": "ok",
        "service": "browser-eye",
        "ready": True,
        "global_web_search": bool(os.environ.get("GLOBAL_SEARCH_BROWSER_TOKEN")),
        **RUNTIME.diagnostics(),
    })


# Replace the existing lightweight Flask view while retaining the same /health
# route and endpoint name. Normal application imports remain Playwright-free;
# only the dedicated service entrypoint activates this readiness contract.
app.view_functions["health"] = ready_health


__all__ = ["app"]
