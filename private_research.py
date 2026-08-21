"""Private-session endpoint for read-only source evidence inspection."""
from __future__ import annotations

from typing import Callable

from flask import jsonify, request

from private_mode import _config, _session_active
from research_evidence import fetch_research_evidence, research_evidence_capabilities


DEFAULT_EVIDENCE_LIMIT = "20 per minute"


def _private_active() -> bool:
    return _session_active(_config())


def _hide():
    return jsonify({"error": "Not found"}), 404


def install_private_research_routes(
    app,
    app_module=None,
    *,
    evidence_fetcher: Callable = fetch_research_evidence,
):
    if getattr(app, "_namemachine_private_research_installed", False):
        return
    app._namemachine_private_research_installed = True

    limiter = getattr(app_module, "limiter", None)

    def evidence_view():
        if not _private_active():
            return _hide()
        payload = request.get_json(silent=True)
        payload = payload if isinstance(payload, dict) else {}
        url = str(payload.get("url") or "").strip()
        if not url:
            return jsonify({"error": "Source URL is required"}), 400
        if len(url) > 2000:
            return jsonify({"error": "Source URL is too long"}), 400
        try:
            result = evidence_fetcher(url)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except Exception:
            app.logger.exception("Private research evidence fetch failed")
            return jsonify({"error": "Temporary evidence retrieval error"}), 503
        status = str(result.get("provider_status") or "") if isinstance(result, dict) else ""
        code = 503 if status in {"unconfigured", "rate_limited"} or status.startswith("provider_http_5") else 200
        return jsonify(result), code

    if limiter is not None:
        evidence_view = limiter.limit(DEFAULT_EVIDENCE_LIMIT)(evidence_view)

    app.add_url_rule(
        "/api/private-mode/evidence",
        endpoint="private_mode_evidence",
        view_func=evidence_view,
        methods=["POST"],
    )


def private_research_diagnostics() -> dict:
    payload = research_evidence_capabilities()
    payload["private_session_required"] = True
    payload["endpoint_hidden_when_locked"] = True
    return payload


__all__ = [
    "install_private_research_routes",
    "private_research_diagnostics",
]
