"""Authenticated ingestion for short-lived internal NameMachine telemetry."""

from __future__ import annotations

import json
import re

from flask import jsonify, request

from audit_store import AUDIT_RETENTION_DAYS, AUDIT_STORE


TOKEN_HEADER = "X-NameMachine-Session-Token"
MAX_AUDIT_EVENTS = 100
MAX_EVENT_BYTES = 5000
MAX_BATCH_BYTES = 80000
EVENT_TYPE_RE = re.compile(r"^[a-z0-9_:-]{1,48}$")


def _clean_event(raw):
    if not isinstance(raw, dict):
        return None
    event_type = str(raw.get("type") or "").strip().lower()[:48]
    if not EVENT_TYPE_RE.fullmatch(event_type):
        return None
    details = raw.get("details") if isinstance(raw.get("details"), dict) else {}
    clean = {
        "at": str(raw.get("at") or "")[:64],
        "type": event_type,
        "job_id": str(raw.get("job_id") or "")[:96] or None,
        "details": details,
    }
    encoded = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_EVENT_BYTES:
        return None
    return clean


def install_audit_routes(app, app_module):
    if "api_audit_retention" in app.view_functions:
        return

    @app.get("/api/audit-retention")
    def api_audit_retention():
        return jsonify({
            **AUDIT_STORE.diagnostics(),
            "retention_days": AUDIT_RETENTION_DAYS,
            "cleanup": "background worker sweeps expired telemetry; ingestion also prunes opportunistically",
        })

    @app.post("/api/sessions/<session_id>/audit-events/batch")
    @app_module.limiter.limit("120 per minute")
    def api_ingest_audit_events(session_id):
        if not AUDIT_STORE.configured:
            return jsonify({"error": "Audit storage is not configured"}), 503
        data = app_module.json_object()
        if data is None:
            return jsonify({"error": "JSON body must be an object"}), 400
        raw_events = data.get("events")
        if not isinstance(raw_events, list) or not raw_events:
            return jsonify({"error": "events must be a non-empty list"}), 400
        if len(raw_events) > MAX_AUDIT_EVENTS:
            return jsonify({"error": f"At most {MAX_AUDIT_EVENTS} events per batch"}), 400
        if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > MAX_BATCH_BYTES:
            return jsonify({"error": "Audit batch is too large"}), 413
        events = [event for event in (_clean_event(raw) for raw in raw_events) if event]
        if not events:
            return jsonify({"error": "No valid audit events"}), 400
        try:
            result = AUDIT_STORE.upsert_events(session_id, request.headers.get(TOKEN_HEADER, ""), events)
            try:
                AUDIT_STORE.prune_expired()
            except Exception:
                pass
        except Exception as error:
            app.logger.warning("Audit event persistence failed: %s", type(error).__name__)
            return jsonify({"error": "Audit storage unavailable"}), 503
        if result is None:
            return jsonify({"error": "Session not found"}), 404
        return jsonify(result)


__all__ = ["install_audit_routes"]
