"""Session-authenticated persistence routes for resource-specific variant checks."""

from __future__ import annotations

import os

from flask import jsonify, request

from session_api import TOKEN_HEADER
from variant_store import VARIANT_STORE


VARIANT_SESSION_RATE_LIMIT = os.environ.get("VARIANT_SESSION_RATE_LIMIT", "120 per minute")


def install_variant_session_routes(app, app_module):
    if "api_get_variant_expansion" in app.view_functions:
        return

    def token():
        return request.headers.get(TOKEN_HEADER, "")

    def unavailable():
        return jsonify({
            "error": "Durable variant storage requires configured session storage.",
            "error_type": "VariantStorageUnavailable",
        }), 503

    @app.get("/api/variant-expansion-storage")
    def api_variant_expansion_storage():
        diagnostics = VARIANT_STORE.diagnostics()
        return jsonify({**diagnostics, "enabled": bool(diagnostics["configured"])})

    @app.get("/api/sessions/<session_id>/variant-expansions/<parent_name>")
    @app_module.limiter.limit(VARIANT_SESSION_RATE_LIMIT)
    def api_get_variant_expansion(session_id, parent_name):
        if not VARIANT_STORE.configured:
            return unavailable()
        try:
            expansion = VARIANT_STORE.get(session_id, token(), parent_name)
        except Exception as error:
            app.logger.warning("Variant expansion read failed: %s", type(error).__name__)
            return unavailable()
        if expansion is None:
            return jsonify({"error": "Session not found or token invalid"}), 404
        if expansion is False:
            return jsonify({"expansion": None}), 200
        return jsonify({"expansion": expansion})

    @app.put("/api/sessions/<session_id>/variant-expansions/<parent_name>")
    @app_module.limiter.limit(VARIANT_SESSION_RATE_LIMIT)
    def api_put_variant_expansion(session_id, parent_name):
        if not VARIANT_STORE.configured:
            return unavailable()
        data = app_module.json_object()
        if data is None:
            return jsonify({"error": "JSON body must be an object"}), 400
        try:
            expansion = VARIANT_STORE.upsert(session_id, token(), parent_name, data)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except Exception as error:
            app.logger.warning("Variant expansion write failed: %s", type(error).__name__)
            return unavailable()
        if expansion is None:
            return jsonify({"error": "Session not found or token invalid"}), 404
        return jsonify({"expansion": expansion}), 200


__all__ = ["VARIANT_SESSION_RATE_LIMIT", "install_variant_session_routes"]
