"""HTTP API for durable long-running NameMachine searches."""

from __future__ import annotations

import os

from flask import jsonify, request

from background_jobs import JOB_STORE, MAX_BACKGROUND_TARGET, MAX_BATCH_SIZE
from candidate_feed import CandidateFeedStore, MAX_FEED_PAGE
from session_api import TOKEN_HEADER
from worker_heartbeat import status as worker_status


BACKGROUND_CREATE_RATE_LIMIT = os.environ.get("BACKGROUND_CREATE_RATE_LIMIT", "30 per minute")
BACKGROUND_READ_RATE_LIMIT = os.environ.get("BACKGROUND_READ_RATE_LIMIT", "180 per minute")


def background_search_diagnostics():
    diagnostics = JOB_STORE.diagnostics()
    heartbeat = worker_status(JOB_STORE.session_store) if JOB_STORE.configured else {
        "worker_online": False,
        "worker_count": 0,
        "last_seen_at": None,
    }
    return {**diagnostics, **heartbeat}


def install_background_search_routes(app, app_module):
    if "api_background_search_capabilities" in app.view_functions:
        return

    def token():
        return request.headers.get(TOKEN_HEADER, "")

    def unavailable():
        return jsonify({
            "error": "Durable background search requires configured session storage.",
            "error_type": "BackgroundSearchUnavailable",
        }), 503

    @app.get("/api/background-search")
    def api_background_search_capabilities():
        diagnostics = background_search_diagnostics()
        configured = bool(diagnostics["configured"])
        return jsonify({
            **diagnostics,
            "enabled": configured,
            "ready": configured and bool(diagnostics.get("worker_online")),
            "token_header": TOKEN_HEADER,
        })

    @app.post("/api/sessions/<session_id>/search-jobs")
    @app_module.limiter.limit(BACKGROUND_CREATE_RATE_LIMIT)
    def api_create_background_job(session_id):
        if not JOB_STORE.configured:
            return unavailable()
        data = app_module.json_object()
        if data is None:
            return jsonify({"error": "JSON body must be an object"}), 400

        brief, brand_dna, search_context, error_response = app_module.validate_generation_input(data)
        if error_response:
            return error_response
        try:
            resources = app_module.normalize_resources(data.get("resources"))
            required_resources = app_module.normalize_required_resources(
                data.get("required_resources"), resources
            )
            generation_context = app_module.clean_generation_context(data.get("generation_context"))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        try:
            target_count = int(data.get("target_count", 500))
            batch_size = int(data.get("batch_size", 20))
        except (TypeError, ValueError):
            return jsonify({"error": "target_count and batch_size must be integers"}), 400
        if target_count < 1 or target_count > MAX_BACKGROUND_TARGET:
            return jsonify({"error": f"target_count must be between 1 and {MAX_BACKGROUND_TARGET}"}), 400
        if batch_size < 1 or batch_size > MAX_BATCH_SIZE:
            return jsonify({"error": f"batch_size must be between 1 and {MAX_BATCH_SIZE}"}), 400

        payload = {
            "run_id": str(data.get("run_id") or "")[:96],
            "prompt": brief,
            "resources": resources,
            "required_resources": required_resources,
            "preferences": app_module.clean_preferences(data.get("preferences")),
            "search_context": search_context,
            "brand_dna": brand_dna,
            "generation_context": generation_context,
            "target_count": target_count,
            "batch_size": batch_size,
        }
        if data.get("max_batches") is not None:
            try:
                payload["max_batches"] = int(data.get("max_batches"))
            except (TypeError, ValueError):
                return jsonify({"error": "max_batches must be an integer"}), 400

        try:
            job = JOB_STORE.enqueue(session_id, token(), payload)
        except Exception as error:
            app.logger.warning("Background search enqueue failed: %s", type(error).__name__)
            return unavailable()
        if job is None:
            return jsonify({"error": "Session not found"}), 404
        return jsonify({"job": job}), 202

    @app.get("/api/sessions/<session_id>/search-jobs")
    @app_module.limiter.limit(BACKGROUND_READ_RATE_LIMIT)
    def api_list_background_jobs(session_id):
        if not JOB_STORE.configured:
            return unavailable()
        try:
            limit = int(request.args.get("limit", "20"))
        except ValueError:
            limit = 20
        try:
            jobs = JOB_STORE.list(session_id, token(), limit=limit)
        except Exception as error:
            app.logger.warning("Background search list failed: %s", type(error).__name__)
            return unavailable()
        if jobs is None:
            return jsonify({"error": "Session not found"}), 404
        return jsonify({"jobs": jobs})

    @app.get("/api/sessions/<session_id>/search-jobs/<job_id>")
    @app_module.limiter.limit(BACKGROUND_READ_RATE_LIMIT)
    def api_get_background_job(session_id, job_id):
        if not JOB_STORE.configured:
            return unavailable()
        try:
            job = JOB_STORE.get(session_id, token(), job_id)
        except Exception as error:
            app.logger.warning("Background search read failed: %s", type(error).__name__)
            return unavailable()
        if job is None:
            return jsonify({"error": "Job not found"}), 404
        return jsonify({"job": job})

    @app.post("/api/sessions/<session_id>/search-jobs/<job_id>/cancel")
    @app_module.limiter.limit(BACKGROUND_CREATE_RATE_LIMIT)
    def api_cancel_background_job(session_id, job_id):
        if not JOB_STORE.configured:
            return unavailable()
        try:
            job = JOB_STORE.cancel(session_id, token(), job_id)
        except Exception as error:
            app.logger.warning("Background search cancel failed: %s", type(error).__name__)
            return unavailable()
        if job is None:
            return jsonify({"error": "Job not found"}), 404
        return jsonify({"job": job})

    @app.get("/api/sessions/<session_id>/candidate-feed")
    @app_module.limiter.limit(BACKGROUND_READ_RATE_LIMIT)
    def api_candidate_feed(session_id):
        if not JOB_STORE.configured:
            return unavailable()
        try:
            after_seq = int(request.args.get("after_seq", "0"))
            limit = int(request.args.get("limit", "100"))
        except ValueError:
            return jsonify({"error": "after_seq and limit must be integers"}), 400
        if after_seq < 0:
            return jsonify({"error": "after_seq must be non-negative"}), 400
        if limit < 1 or limit > MAX_FEED_PAGE:
            return jsonify({"error": f"limit must be between 1 and {MAX_FEED_PAGE}"}), 400
        try:
            feed = CandidateFeedStore(JOB_STORE.session_store).since(
                session_id,
                token(),
                after_seq=after_seq,
                limit=limit,
            )
        except Exception as error:
            app.logger.warning("Candidate feed read failed: %s", type(error).__name__)
            return unavailable()
        if feed is None:
            return jsonify({"error": "Session not found"}), 404
        return jsonify(feed)


__all__ = ["background_search_diagnostics", "install_background_search_routes"]
