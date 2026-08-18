"""HTTP feed for short-lived durable background candidate lifecycle events."""
from __future__ import annotations

import os

from flask import jsonify, request

from durable_candidate_events import LIVE_CANDIDATES, MAX_EVENT_PAGE
from session_api import TOKEN_HEADER


EVENT_READ_RATE_LIMIT = os.environ.get("CANDIDATE_EVENT_READ_RATE_LIMIT", "240 per minute")


def install_candidate_event_routes(app, app_module):
    if "api_candidate_events" in app.view_functions:
        return

    @app.get("/api/sessions/<session_id>/candidate-events")
    @app_module.limiter.limit(EVENT_READ_RATE_LIMIT)
    def api_candidate_events(session_id):
        if not LIVE_CANDIDATES.configured:
            return jsonify({
                "error": "Durable candidate events require configured session storage.",
                "error_type": "CandidateEventsUnavailable",
            }), 503
        try:
            after_seq = int(request.args.get("after_seq", "0"))
            limit = int(request.args.get("limit", "100"))
        except ValueError:
            return jsonify({"error": "after_seq and limit must be integers"}), 400
        if after_seq < 0:
            return jsonify({"error": "after_seq must be non-negative"}), 400
        if limit < 1 or limit > MAX_EVENT_PAGE:
            return jsonify({"error": f"limit must be between 1 and {MAX_EVENT_PAGE}"}), 400
        try:
            feed = LIVE_CANDIDATES.since(
                session_id,
                request.headers.get(TOKEN_HEADER, ""),
                after_seq=after_seq,
                limit=limit,
            )
        except Exception as error:
            app.logger.warning("Candidate event feed read failed: %s", type(error).__name__)
            return jsonify({
                "error": "Temporary candidate event feed error.",
                "error_type": type(error).__name__,
            }), 503
        if feed is None:
            return jsonify({"error": "Session not found"}), 404
        return jsonify(feed)


__all__ = ["install_candidate_event_routes"]
