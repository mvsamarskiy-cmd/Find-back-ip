"""Verify an existing NameMachine candidate set without generating new names."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from flask import jsonify, request

from identity_bundle import classify_identity_bundle


MAX_RECHECK_NAMES = 250
RECHECK_RATE_LIMIT = "12 per minute"


def _clean_handle(value):
    raw = str(value or "").strip().lstrip("@")
    return re.sub(r"[^A-Za-z0-9_]", "", raw)[:32]


def install_recheck_routes(app, app_module):
    if "api_recheck_candidates" in app.view_functions:
        return

    @app.post("/api/recheck")
    @app_module.limiter.limit(RECHECK_RATE_LIMIT)
    def api_recheck_candidates():
        data = app_module.json_object()
        if data is None:
            return jsonify({"error": "JSON body must be an object"}), 400

        raw_names = data.get("names")
        if not isinstance(raw_names, list):
            return jsonify({"error": "names must be a list"}), 400

        names = []
        seen = set()
        for raw in raw_names[:MAX_RECHECK_NAMES]:
            name = _clean_handle(raw)
            key = name.lower()
            if len(name) < 3 or key in seen:
                continue
            seen.add(key)
            names.append(name)
        if not names:
            return jsonify({"error": "No valid names to recheck"}), 400

        try:
            resources = app_module.normalize_resources(data.get("resources"))
            required = app_module.normalize_required_resources(
                data.get("required_resources"), resources
            )
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        try:
            checks = app_module.check_many(names, resources=resources)
            rows = []
            for name, payload in zip(names, checks):
                row = {"name": name, "checked": True}
                if isinstance(payload, dict):
                    row.update(payload)
                row.update(classify_identity_bundle(row.get("availability"), required))
                row["rechecked_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                row["recheck_resources"] = list(resources)
                rows.append(row)
            return jsonify({
                "rows": rows,
                "checked": len(rows),
                "resources": list(resources),
                "required_resources": list(required),
            })
        except Exception as error:
            app.logger.exception("Candidate recheck failed")
            return jsonify({
                "error": "Temporary verification error. Please try again.",
                "error_type": type(error).__name__,
            }), 503


__all__ = ["MAX_RECHECK_NAMES", "install_recheck_routes"]
