"""Incremental AI generation + resource-level verification delivery.

The historical JSON endpoint remains intact for compatibility. This module adds
an NDJSON endpoint where generated candidates are emitted immediately, selected
resources are checked in one bounded pool, and every completed resource is sent
to the browser before the candidate's final bundle verdict is assembled.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os

from flask import Response, jsonify, stream_with_context


def _bounded_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


STREAM_RESOURCE_WORKERS = _bounded_int("STREAM_RESOURCE_WORKERS", 12, 2, 24)
STATUS_VALUES = (
    "claimable",
    "purchasable",
    "taken",
    "not_found",
    "invalid",
    "reserved",
    "rate_limited",
    "unknown",
)
ACTIONABLE_STATUSES = frozenset({"claimable", "purchasable"})
UNRESOLVED_STATUSES = frozenset({"rate_limited", "unknown"})


def _event(event_type, **payload):
    return json.dumps(
        {"type": event_type, **payload},
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n"


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _generate_candidates(
    app_module,
    brief,
    count,
    data,
    brand_dna,
    search_context,
    generation_context,
    resources,
):
    if os.environ.get("OPENAI_API_KEY"):
        brief, search_context, _intelligence = app_module.apply_prompt_intelligence(
            brief,
            resources,
            search_context,
        )

    last_error = None
    for attempt in range(3):
        try:
            return app_module.generate_ai_with_context(
                brief,
                count,
                app_module.clean_preferences(data.get("preferences")),
                brand_dna,
                search_context,
                generation_context,
            )
        except Exception as error:  # preserve the current retry behavior
            last_error = error
            app_module.app.logger.warning(
                "Streaming AI generation attempt %s failed: %s",
                attempt + 1,
                type(error).__name__,
            )
    raise last_error


def _unknown_verdict(resource, name, reason="Resource verification failed closed."):
    return {
        "platform": resource,
        "handle": str(name).strip().lower(),
        "verdict": "unknown",
        "confidence": 0.0,
        "evidence": [],
        "reason": reason,
    }


def _failed_resource_part(name, resource):
    return {
        "availability": {
            "status": "unknown",
            "detail": "Resource verification failed closed; retry is allowed.",
            "url": "",
            "source": "streaming_runtime",
            "method": "single_resource_check",
            "confidence": 0.0,
            "occupancy": "unknown",
            "claimability": "unconfirmed",
            "checked_at": _now(),
        },
        "verification": _unknown_verdict(resource, name),
        "error": True,
    }


def _check_resource(app_module, name, resource):
    """Check exactly one selected resource and return its normalized v2 part."""
    payload = app_module.check_all(name, resources=[resource])
    if not isinstance(payload, dict):
        raise TypeError("Resource checker returned a non-object payload")

    availability = payload.get("availability") or {}
    row = availability.get(resource) if isinstance(availability, dict) else None
    if not isinstance(row, dict):
        raise ValueError("Resource checker omitted its availability row")

    verification_map = payload.get("verification") or {}
    verdict = verification_map.get(resource) if isinstance(verification_map, dict) else None
    if not isinstance(verdict, dict):
        verdict = _unknown_verdict(
            resource,
            name,
            "Availability row exists but no Verification v2 verdict was returned.",
        )

    return {
        "availability": dict(row),
        "verification": dict(verdict),
        "error": False,
    }


def _aggregate_counts(availability):
    statuses = []
    for row in availability.values():
        status = str((row or {}).get("status") or "unknown") if isinstance(row, dict) else "unknown"
        statuses.append(status if status in STATUS_VALUES else "unknown")

    status_counts = {status: statuses.count(status) for status in STATUS_VALUES}
    total = len(statuses)
    claimable_count = status_counts["claimable"]
    purchasable_count = status_counts["purchasable"]
    actionable_count = sum(status_counts[status] for status in ACTIONABLE_STATUSES)
    unresolved_count = sum(status_counts[status] for status in UNRESOLVED_STATUSES)
    return {
        "status_counts": status_counts,
        "claimable_count": claimable_count,
        "purchasable_count": purchasable_count,
        "actionable_count": actionable_count,
        "not_found_count": status_counts["not_found"],
        "taken_count": status_counts["taken"],
        "invalid_count": status_counts["invalid"],
        "reserved_count": status_counts["reserved"],
        "rate_limited_count": status_counts["rate_limited"],
        "unknown_count": status_counts["unknown"],
        "unresolved_count": unresolved_count,
        "total_resources": total,
        "all_claimable": bool(total) and claimable_count == total,
        "all_verified": bool(total) and unresolved_count == 0,
        "available_count": actionable_count,
        "all_available": bool(total) and actionable_count == total,
    }


def _finalize_candidate(app_module, source_row, resources, required_resources, parts):
    result = dict(source_row or {})
    name = str(result.get("name") or "").strip()
    availability = {}
    verification = {}
    for resource in resources:
        part = parts.get(resource) or _failed_resource_part(name, resource)
        availability[resource] = dict(part["availability"])
        verification[resource] = dict(part["verification"])

    result["availability"] = availability
    result["verification"] = verification
    result.update(_aggregate_counts(availability))
    result.update(
        app_module.classify_identity_bundle(
            availability,
            required_resources,
        )
    )
    result["trademark"] = app_module.trademark_links(name)
    return result


def install_streaming_routes(app, app_module):
    """Install the incremental endpoint on the already-configured Flask app."""

    @app.post("/api/ai-generate-stream")
    @app_module.limiter.limit(app_module.AI_RATE_LIMIT)
    def api_ai_generate_stream():
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
        except ValueError as error:
            return app_module.resource_error(error)

        try:
            generation_context = app_module.clean_generation_context(data.get("generation_context"))
        except ValueError as error:
            return app_module.generation_context_error(error)

        try:
            count = max(1, min(20, int(data.get("count", 10))))
        except (ValueError, TypeError):
            count = 10

        if not app_module.AI_REQUEST_SLOTS.acquire(blocking=False):
            return jsonify({
                "error": "AI is busy. Please try again in a few seconds.",
                "retry_after": 5,
            }), 503, {"Retry-After": "5"}

        try:
            names = _generate_candidates(
                app_module,
                brief,
                count,
                data,
                brand_dna,
                search_context,
                generation_context,
                resources,
            )
        except Exception as error:
            app_module.app.logger.exception("Streaming AI generation failed")
            return jsonify({
                "error": "Temporary AI error. Please tap Generate again.",
                "error_type": type(error).__name__,
            }), 503
        finally:
            app_module.AI_REQUEST_SLOTS.release()

        rows = [row for row in (names or []) if isinstance(row, dict) and row.get("name")]

        @stream_with_context
        def generate_stream():
            total_candidates = len(rows)
            total_checks = total_candidates * len(resources)
            yield _event(
                "phase",
                phase="generated",
                total=total_candidates,
                total_resource_checks=total_checks,
            )
            if not rows:
                yield _event(
                    "done",
                    total=0,
                    completed=0,
                    delivered=0,
                    errors=0,
                    completed_resource_checks=0,
                    total_resource_checks=0,
                )
                return

            prepared = []
            for index, row in enumerate(rows):
                source_row = dict(row)
                name = str(source_row.get("name") or "").strip()
                candidate_id = f"{index}:{name.lower()}"
                source_row["trademark"] = app_module.trademark_links(name)
                prepared.append((candidate_id, source_row))
                yield _event(
                    "candidate",
                    candidate_id=candidate_id,
                    row=source_row,
                    resources=list(resources),
                    index=index,
                    total=total_candidates,
                )

            yield _event(
                "phase",
                phase="verifying",
                total=total_candidates,
                total_resource_checks=total_checks,
            )

            workers = max(2, min(STREAM_RESOURCE_WORKERS, total_checks))
            executor = ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="stream-resource",
            )
            futures = {}
            parts_by_candidate = {candidate_id: {} for candidate_id, _row in prepared}
            source_by_candidate = {candidate_id: row for candidate_id, row in prepared}
            completed_candidates = set()

            for candidate_id, row in prepared:
                name = str(row.get("name") or "").strip()
                for resource in resources:
                    future = executor.submit(
                        _check_resource,
                        app_module,
                        name,
                        resource,
                    )
                    futures[future] = (candidate_id, name, resource)

            completed_checks = 0
            delivered = 0
            errors = 0
            try:
                for future in as_completed(futures):
                    candidate_id, name, resource = futures[future]
                    completed_checks += 1
                    try:
                        part = future.result()
                    except Exception as error:
                        errors += 1
                        app_module.app.logger.warning(
                            "Streaming resource verification failed for %s/%s: %s",
                            name[:40],
                            resource,
                            type(error).__name__,
                        )
                        part = _failed_resource_part(name, resource)

                    parts = parts_by_candidate[candidate_id]
                    parts[resource] = part
                    yield _event(
                        "resource",
                        candidate_id=candidate_id,
                        name=name,
                        resource=resource,
                        availability=part["availability"],
                        verification=part["verification"],
                        error=bool(part.get("error")),
                        completed_resources=len(parts),
                        total_resources=len(resources),
                        completed_resource_checks=completed_checks,
                        total_resource_checks=total_checks,
                    )

                    if len(parts) == len(resources) and candidate_id not in completed_candidates:
                        completed_candidates.add(candidate_id)
                        delivered += 1
                        final_row = _finalize_candidate(
                            app_module,
                            source_by_candidate[candidate_id],
                            resources,
                            required_resources,
                            parts,
                        )
                        yield _event(
                            "result",
                            candidate_id=candidate_id,
                            row=final_row,
                            completed=delivered,
                            total=total_candidates,
                        )

                yield _event(
                    "done",
                    total=total_candidates,
                    completed=len(completed_candidates),
                    delivered=delivered,
                    errors=errors,
                    completed_resource_checks=completed_checks,
                    total_resource_checks=total_checks,
                )
            except GeneratorExit:
                return
            finally:
                for future in futures:
                    future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)

        response = Response(
            generate_stream(),
            content_type="application/x-ndjson; charset=utf-8",
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["X-Accel-Buffering"] = "no"
        return response


__all__ = ["install_streaming_routes"]
