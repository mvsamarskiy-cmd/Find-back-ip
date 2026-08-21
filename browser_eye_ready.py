"""Readiness wrapper for the private Browser Eye service.

Railway must not mark the service healthy merely because Flask/Gunicorn booted.
The readiness probe warms Playwright and launches both Chromium and WebKit once.
Tor is additive: when enabled, readiness also requires the local SOCKS listener,
while full Tor-network bootstrap is visible in daemon logs and can be exercised by
private Tor routes without making normal Browser Eye dependent on external Tor exits.
"""
from __future__ import annotations

import os

from flask import jsonify

import browser_eye_service as browser_eye_module
import browser_eye_tor as browser_eye_tor_module
from browser_eye_global_search import install_browser_global_search
from browser_eye_hardening import install_browser_eye_hardening
from browser_eye_service import RUNTIME, app
from browser_eye_tor import install_browser_tor_routes, tor_diagnostics, wait_for_tor_socket
from browser_eye_tor_hardening import install_tor_hardening


install_browser_eye_hardening(browser_eye_module)
install_tor_hardening(browser_eye_tor_module)
install_browser_global_search(app, RUNTIME)
install_browser_tor_routes(app, RUNTIME)


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
    if not wait_for_tor_socket(timeout=8.0):
        return jsonify({
            "status": "error",
            "service": "browser-eye",
            "ready": False,
            "error_type": "TorSocksUnavailable",
            "tor": browser_eye_tor_module.tor_diagnostics(),
        }), 503
    return jsonify({
        "status": "ok",
        "service": "browser-eye",
        "ready": True,
        "global_web_search": bool(os.environ.get("GLOBAL_SEARCH_BROWSER_TOKEN")),
        "tor": browser_eye_tor_module.tor_diagnostics(),
        **RUNTIME.diagnostics(),
    })


app.view_functions["health"] = ready_health


__all__ = ["app"]
