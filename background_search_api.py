"""HTTP API for durable long-running NameMachine searches."""

from __future__ import annotations

import os

from flask import jsonify, request

from availability_hunter import HUNTER_KEY, MAX_TARGET_MATCHES, STRICT_MATCH_POLICY
from background_job_guardrails import (
    BackgroundJobLimitError,
    admission_diagnostics,
    admit_and_enqueue,
)
from background_jobs import JOB_STORE, MAX_BACKGROUND_TARGET, MAX_BATCH_SIZE
from candidate_feed import CandidateFeedStore, MAX_FEED_PAGE
from procedural_search import PROCEDURAL_KEY, STRATEGIES
from session_api import TOKEN_HEADER
from worker_heartbeat import status as worker_status


BACKGROUND_CREATE_RATE_LIMIT = os.environ.get("BACKGROUND_CREATE_RATE_LIMIT", "30 per minute")
BACKGROUND_READ_RATE_LIMIT = os.environ.get("BACKGROUND_READ_RATE_LIMIT", "180 per minute")
TURBO_GUIDANCE = (
    "Turbo search: maximize lexical and phonetic breadth across the interpreted semantic territory. "
    "Do not linger on one root or make tiny mutations of occupied names. The objective is strict-free yield, not a pretty brainstorm list."
)


def background_search_diagnostics():
    diagnostics = JOB_STORE.diagnostics()
    heartbeat = worker_status(JOB_STORE.session_store) if JOB_STORE.configured else {
        "worker_online": False,
        "worker_count": 0,
        "last_seen_at": None,
    }
    return {
        **diagnostics,
        **heartbeat,
        "admission_control": admission_diagnostics(),
        "availability_hunter": {
            "supported": True,
            "target_matches_max": MAX_TARGET_MATCHES,
            "max_checks_max": MAX_BACKGROUND_TARGET,
            "strict_match_policy": STRICT_MATCH_POLICY,
            "purchasable_counts_as_free_match": False,
            "not_found_counts_as_free_match": False,
        },
        "procedural_search": {
            "supported": True,
            "default_for_hunter": True,
            "one_root_at_a_time": True,
            "strategies": list(STRATEGIES),
            "uses_real_verification_yield": True,
        },
        "turbo_search": {
            "supported": True,
            "broad_exploration": True,
            "primary_feed_strict_free_only": True,
            "strict_match_policy": STRICT_MATCH_POLICY,
            "rejected_rows_remain_durable": True,
        },
    }


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

        target_matches_raw = data.get("target_matches")
        if target_matches_raw is not None:
            try:
                target_matches = int(target_matches_raw)
                max_checks = int(data.get("max_checks", target_count))
            except (TypeError, ValueError):
                return jsonify({"error": "target_matches and max_checks must be integers"}), 400
            if target_matches < 1 or target_matches > MAX_TARGET_MATCHES:
                return jsonify({"error": f"target_matches must be between 1 and {MAX_TARGET_MATCHES}"}), 400
            if max_checks < 1 or max_checks > MAX_BACKGROUND_TARGET:
                return jsonify({"error": f"max_checks must be between 1 and {MAX_BACKGROUND_TARGET}"}), 400
            if target_matches > max_checks:
                return jsonify({"error": "target_matches cannot exceed max_checks"}), 400

            strategy = str(data.get("search_strategy") or "procedural").strip().lower()
            if strategy not in {"procedural", "adaptive", "turbo"}:
                return jsonify({"error": "search_strategy must be procedural, turbo, or adaptive"}), 400

            search_context = dict(search_context or {})
            search_context[HUNTER_KEY] = {
                "enabled": True,
                "target_matches": target_matches,
                "max_checks": max_checks,
                "match_policy": STRICT_MATCH_POLICY,
            }
            search_context["search_strategy"] = strategy
            if strategy == "procedural":
                search_context[PROCEDURAL_KEY] = {
                    "enabled": True,
                    "strategy": "procedural",
                }
            elif strategy == "turbo":
                existing_guidance = str(search_context.get("guidance") or "").strip()
                search_context["guidance"] = " | ".join(
                    part for part in [existing_guidance, TURBO_GUIDANCE] if part
                )[:500]
                search_context["turbo_search"] = {
                    "enabled": True,
                    "strict_free_primary_feed": True,
                }
            target_count = max_checks

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
            job = admit_and_enqueue(JOB_STORE, session_id, token(), payload)
        except BackgroundJobLimitError as error:
            body = {
                "error": str(error),
                "error_type": "BackgroundSearchLimitExceeded",
                "limit_code": error.code,
                "retry_after": error.retry_after,
                **error.details,
            }
            return jsonify(body), error.http_status, {"Retry-After": str(error.retry_after)}
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
