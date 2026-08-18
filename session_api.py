"""HTTP API for durable anonymous NameMachine sessions.

A session is protected by an unguessable capability token returned only when the
server session is created. The token is sent in a header and stored only as a
SHA-256 hash in the database. No account system is required for this first
persistence layer.
"""

from __future__ import annotations

import json
import os
import re

from flask import jsonify, request

from session_store import SCHEMA_VERSION, STORE


SESSION_RATE_LIMIT = os.environ.get("SESSION_RATE_LIMIT", "180 per minute")
TOKEN_HEADER = "X-NameMachine-Session-Token"
MAX_CANDIDATE_BATCH = 8
MAX_CANDIDATE_BYTES = 12000


def _text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _name(value, limit=96):
    return re.sub(r"[^A-Za-z0-9._-]", "", str(value or ""))[:limit]


def _bounded_list(value, limit, cleaner=None):
    if not isinstance(value, list):
        return []
    output = []
    for item in value[:limit]:
        clean = cleaner(item) if cleaner else item
        if clean in (None, "", {}):
            continue
        output.append(clean)
    return output


def _clean_prompt(row):
    if not isinstance(row, dict):
        return None
    text = _text(row.get("text"), 1000)
    if not text:
        return None
    feedback = row.get("feedback") if isinstance(row.get("feedback"), list) else []
    result = {
        "text": text,
        "at": str(row.get("at") or "")[:64],
        "feedback": feedback[:50],
    }
    entry_mode = _text(row.get("entry_mode"), 32)
    if entry_mode:
        result["entry_mode"] = entry_mode
    return result


def _clean_run(row):
    if not isinstance(row, dict):
        return None
    run_id = _name(row.get("id"))
    if not run_id:
        return None
    allowed = {
        "id": run_id,
        "prompt": _text(row.get("prompt"), 1000),
        "started": str(row.get("started") or "")[:64],
        "finished": str(row.get("finished") or "")[:64],
        "status": _text(row.get("status"), 24),
    }
    entry_mode = _text(row.get("entry_mode"), 32)
    if entry_mode:
        allowed["entry_mode"] = entry_mode
    for key in ("startResultCount", "endResultCount", "startBatch", "endBatch"):
        try:
            allowed[key] = max(0, int(row.get(key) or 0))
        except (TypeError, ValueError):
            allowed[key] = 0
    return allowed


def _clean_feedback(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for raw_name, row in list(value.items())[:500]:
        key = _name(raw_name).lower()
        if not key or not isinstance(row, dict):
            continue
        try:
            vote = int(row.get("vote") or 0)
        except (TypeError, ValueError):
            vote = 0
        result[key] = {
            "vote": 1 if vote > 0 else -1 if vote < 0 else 0,
            "comment": _text(row.get("comment"), 300),
        }
    return result


def _clean_metadata(data, app_module):
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    raw_resources = data.get("resources")
    if raw_resources is None:
        resources = []
    else:
        resources = app_module.normalize_resources(raw_resources)
    return {
        "client_session_id": _name(data.get("client_session_id"), 96) or None,
        "title": _text(data.get("title"), 160) or "Нова сесія",
        "prompt_history": _bounded_list(data.get("prompt_history"), 100, _clean_prompt),
        "resources": resources,
        "shortlist": _bounded_list(data.get("shortlist"), 250, lambda item: _name(item)),
        "direction_anchors": _bounded_list(data.get("direction_anchors"), 80, lambda item: _name(item)),
        "runs": _bounded_list(data.get("runs"), 250, _clean_run),
        "feedback": _clean_feedback(data.get("feedback")),
        "batch_counter": max(0, min(1000000, int(data.get("batch_counter") or 0))),
        "created": str(data.get("created") or "")[:64],
        "updated": str(data.get("updated") or "")[:64],
    }


def _clean_counts(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, raw in list(value.items())[:24]:
        safe_key = _name(key, 48)
        if not safe_key:
            continue
        try:
            result[safe_key] = max(0, int(raw or 0))
        except (TypeError, ValueError):
            continue
    return result


def _clean_source(value):
    if not isinstance(value, dict):
        return None
    result = {}
    for key, limit in (
        ("market", 16), ("label", 100), ("url", 500), ("automation", 80),
        ("notice", 300), ("coverage", 240), ("query", 120),
    ):
        clean = _text(value.get(key), limit)
        if clean:
            result[key] = clean
    return result or None


def _clean_brand_collision(value):
    """Persist the useful collision summary, not a large raw provider result dump."""
    if not isinstance(value, dict):
        return None
    result = {
        "candidate": _text(value.get("candidate"), 80),
        "collision_signal": _text(value.get("collision_signal"), 32),
        "clearance_complete": bool(value.get("clearance_complete")),
        "legal_clearance": bool(value.get("legal_clearance")),
        "recommendation": _text(value.get("recommendation"), 80),
        "notice": _text(value.get("notice"), 500),
    }
    coverage = value.get("coverage")
    if isinstance(coverage, dict):
        result["coverage"] = {
            "web_automated": bool(coverage.get("web_automated")),
            "companies_uk_automated": bool(coverage.get("companies_uk_automated")),
            "companies_requested_markets": _bounded_list(
                coverage.get("companies_requested_markets"), 8, lambda item: _text(item, 16)
            ),
            "trademarks_automated": bool(coverage.get("trademarks_automated")),
            "trademark_territories": _bounded_list(
                coverage.get("trademark_territories"), 8, lambda item: _text(item, 16)
            ),
            "nice_classes": _bounded_list(coverage.get("nice_classes"), 45),
        }

    web = value.get("web")
    if isinstance(web, dict):
        result["web"] = {
            "provider": _text(web.get("provider"), 64),
            "configured": bool(web.get("configured")),
            "status": _text(web.get("status"), 32),
            "signal": _text(web.get("signal"), 32),
            "reason": _text(web.get("reason"), 300),
            "counts": _clean_counts(web.get("counts")),
            "manual_search": _text(web.get("manual_search"), 500),
        }

    companies = value.get("companies")
    if isinstance(companies, dict):
        clean_companies = {}
        uk = companies.get("uk")
        if isinstance(uk, dict):
            clean_companies["uk"] = {
                "provider": _text(uk.get("provider"), 64),
                "coverage": _text(uk.get("coverage"), 160),
                "configured": bool(uk.get("configured")),
                "status": _text(uk.get("status"), 32),
                "signal": _text(uk.get("signal"), 32),
                "reason": _text(uk.get("reason"), 300),
                "counts": _clean_counts(uk.get("counts")),
            }
        clean_companies["manual_sources"] = _bounded_list(
            companies.get("manual_sources"), 8, _clean_source
        )
        result["companies"] = clean_companies

    trademarks = value.get("trademarks")
    if isinstance(trademarks, dict):
        clean_sources = {}
        raw_sources = trademarks.get("sources")
        if isinstance(raw_sources, dict):
            for raw_key, raw_source in list(raw_sources.items())[:12]:
                key = _name(raw_key, 48)
                source = _clean_source(raw_source)
                if key and source:
                    clean_sources[key] = source
        result["trademarks"] = {
            "candidate": _text(trademarks.get("candidate"), 80),
            "risk": _text(trademarks.get("risk"), 32),
            "assessment": _text(trademarks.get("assessment"), 64),
            "territories": _bounded_list(
                trademarks.get("territories"), 8, lambda item: _text(item, 16)
            ),
            "nice_classes": _bounded_list(trademarks.get("nice_classes"), 45),
            "notice": _text(trademarks.get("notice"), 500),
            "sources": clean_sources,
            "criteria": _bounded_list(
                trademarks.get("criteria"), 12, lambda item: _text(item, 80)
            ),
        }
    return result


_CANDIDATE_KEYS = {
    "name", "score", "length", "reason", "family", "availability", "verification",
    "bundle_state", "bundle_score", "required_resources", "selected_resources",
    "claimable_count", "purchasable_count", "not_found_count", "taken_count",
    "reserved_count", "invalid_count", "unknown_count", "unresolved_count",
    "trademark", "checked", "run_id", "batch_number", "received_seq", "received_at",
    "_stream_id", "resource_progress", "product_mode", "entry_mode", "pronunciation",
    "language_risks", "verification_state", "lifecycle_event_seq",
    "brand_collision", "brand_collision_checked_at",
}


def _clean_candidate(row, app_module):
    if not isinstance(row, dict):
        return None
    name = _name(row.get("name"))
    if not name:
        return None
    clean = {key: row[key] for key in _CANDIDATE_KEYS if key in row}
    clean["name"] = name
    availability = clean.get("availability")
    if isinstance(availability, dict):
        clean["availability"] = {
            key: value for key, value in availability.items()
            if key in app_module.RESOURCE_KEYS and isinstance(value, dict)
        }
    else:
        clean["availability"] = {}
    verification = clean.get("verification")
    if isinstance(verification, dict):
        clean["verification"] = {
            key: value for key, value in verification.items()
            if key in app_module.RESOURCE_KEYS and isinstance(value, dict)
        }
    else:
        clean["verification"] = {}

    if "product_mode" in clean:
        clean["product_mode"] = _text(clean.get("product_mode"), 32)
    if "entry_mode" in clean:
        clean["entry_mode"] = _text(clean.get("entry_mode"), 32)
    if "pronunciation" in clean:
        clean["pronunciation"] = _text(clean.get("pronunciation"), 120)
    if "language_risks" in clean:
        clean["language_risks"] = _bounded_list(
            clean.get("language_risks"), 8, lambda item: _text(item, 160)
        )
    if "verification_state" in clean:
        state = _text(clean.get("verification_state"), 24)
        clean["verification_state"] = state if state in {"checking", "complete", "interrupted"} else ""
    if "lifecycle_event_seq" in clean:
        try:
            clean["lifecycle_event_seq"] = max(0, int(clean.get("lifecycle_event_seq") or 0))
        except (TypeError, ValueError):
            clean.pop("lifecycle_event_seq", None)
    if "brand_collision_checked_at" in clean:
        clean["brand_collision_checked_at"] = str(clean.get("brand_collision_checked_at") or "")[:64]
    if "brand_collision" in clean:
        collision = _clean_brand_collision(clean.get("brand_collision"))
        if collision:
            clean["brand_collision"] = collision
        else:
            clean.pop("brand_collision", None)

    encoded = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_CANDIDATE_BYTES:
        raise ValueError(f"Candidate {name} payload is too large")
    return clean


def session_storage_diagnostics():
    return STORE.diagnostics()


def install_session_routes(app, app_module):
    if "api_session_storage" in app.view_functions:
        return

    def unavailable():
        return jsonify({
            "error": "Durable session storage is not configured on this server.",
            "error_type": "SessionStorageUnavailable",
        }), 503

    def token():
        return request.headers.get(TOKEN_HEADER, "")

    @app.get("/api/session-storage")
    def api_session_storage():
        diagnostics = session_storage_diagnostics()
        return jsonify({
            **diagnostics,
            "enabled": bool(diagnostics["configured"]),
            "token_header": TOKEN_HEADER,
            "candidate_batch_limit": MAX_CANDIDATE_BATCH,
        })

    @app.post("/api/sessions")
    @app_module.limiter.limit(SESSION_RATE_LIMIT)
    def api_create_session():
        if not STORE.configured:
            return unavailable()
        data = app_module.json_object()
        if data is None:
            return jsonify({"error": "JSON body must be an object"}), 400
        try:
            payload = _clean_metadata(data, app_module)
            created = STORE.create_session(payload)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except Exception as error:
            app.logger.warning("Session create failed: %s", type(error).__name__)
            return unavailable()
        return jsonify({
            "session_id": created["id"],
            "session_token": created["token"],
            "revision": created["revision"],
            "server_updated_at": created["server_updated_at"],
            "schema_version": SCHEMA_VERSION,
        }), 201

    @app.get("/api/sessions/<session_id>")
    @app_module.limiter.limit(SESSION_RATE_LIMIT)
    def api_get_session(session_id):
        if not STORE.configured:
            return unavailable()
        try:
            snapshot = STORE.load_session(session_id, token())
        except Exception as error:
            app.logger.warning("Session load failed: %s", type(error).__name__)
            return unavailable()
        if snapshot is None:
            return jsonify({"error": "Session not found"}), 404
        return jsonify({"session_id": session_id, "session": snapshot})

    @app.put("/api/sessions/<session_id>")
    @app_module.limiter.limit(SESSION_RATE_LIMIT)
    def api_update_session(session_id):
        if not STORE.configured:
            return unavailable()
        data = app_module.json_object()
        if data is None:
            return jsonify({"error": "JSON body must be an object"}), 400
        try:
            payload = _clean_metadata(data, app_module)
            updated = STORE.update_session(session_id, token(), payload)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except Exception as error:
            app.logger.warning("Session metadata update failed: %s", type(error).__name__)
            return unavailable()
        if updated is None:
            return jsonify({"error": "Session not found"}), 404
        return jsonify(updated)

    @app.post("/api/sessions/<session_id>/candidates/batch")
    @app_module.limiter.limit(SESSION_RATE_LIMIT)
    def api_upsert_candidate_batch(session_id):
        if not STORE.configured:
            return unavailable()
        data = app_module.json_object()
        if data is None:
            return jsonify({"error": "JSON body must be an object"}), 400
        raw_rows = data.get("candidates")
        if not isinstance(raw_rows, list) or not raw_rows:
            return jsonify({"error": "candidates must be a non-empty list"}), 400
        if len(raw_rows) > MAX_CANDIDATE_BATCH:
            return jsonify({"error": f"At most {MAX_CANDIDATE_BATCH} candidates per batch"}), 400
        try:
            rows = []
            for raw in raw_rows:
                clean = _clean_candidate(raw, app_module)
                if clean:
                    rows.append(clean)
            updated = STORE.upsert_candidates(session_id, token(), rows)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except Exception as error:
            app.logger.warning("Candidate persistence failed: %s", type(error).__name__)
            return unavailable()
        if updated is None:
            return jsonify({"error": "Session not found"}), 404
        return jsonify(updated)


__all__ = [
    "MAX_CANDIDATE_BATCH",
    "TOKEN_HEADER",
    "install_session_routes",
    "session_storage_diagnostics",
]
