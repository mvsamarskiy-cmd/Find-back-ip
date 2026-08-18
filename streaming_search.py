"""Incremental AI generation + verification delivery for the NameMachine feed.

The existing JSON endpoint remains intact for compatibility. This module installs
an NDJSON endpoint that generates one candidate batch, verifies candidates in a
bounded pool, and yields each completed candidate immediately instead of waiting
for the entire batch to finish.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os

from flask import Response, jsonify, stream_with_context


def _bounded_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


STREAM_VERIFY_WORKERS = _bounded_int("STREAM_VERIFY_WORKERS", 5, 1, 10)


def _event(event_type, **payload):
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False, separators=(",", ":")) + "\n"


def _generate_candidates(app_module, brief, count, data, brand_dna, search_context, generation_context, resources):
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


def _verify_candidate(app_module, row, resources, required_resources):
    result = dict(row or {})
    name = str(result.get("name") or "").strip()
    if not name:
        raise ValueError("Candidate has no name")
    availability = app_module.check_all(name, resources=resources)
    result.update(availability)
    result.update(
        app_module.classify_identity_bundle(
            result.get("availability"),
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
            total = len(rows)
            yield _event("phase", phase="verifying", total=total)
            if not rows:
                yield _event("done", total=0, completed=0, delivered=0, errors=0)
                return

            workers = max(1, min(STREAM_VERIFY_WORKERS, total))
            executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="stream-verify")
            futures = {
                executor.submit(
                    _verify_candidate,
                    app_module,
                    row,
                    resources,
                    required_resources,
                ): row
                for row in rows
            }
            completed = 0
            delivered = 0
            errors = 0
            try:
                for future in as_completed(futures):
                    completed += 1
                    source_row = futures[future]
                    try:
                        verified = future.result()
                    except Exception as error:
                        errors += 1
                        app_module.app.logger.warning(
                            "Streaming candidate verification failed for %s: %s",
                            str(source_row.get("name") or "")[:40],
                            type(error).__name__,
                        )
                        yield _event(
                            "candidate_error",
                            name=str(source_row.get("name") or ""),
                            completed=completed,
                            total=total,
                        )
                        continue

                    delivered += 1
                    yield _event(
                        "result",
                        row=verified,
                        completed=completed,
                        total=total,
                    )
                yield _event(
                    "done",
                    total=total,
                    completed=completed,
                    delivered=delivered,
                    errors=errors,
                )
            except GeneratorExit:
                return
            finally:
                for future in futures:
                    future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)

        response = Response(generate_stream(), content_type="application/x-ndjson; charset=utf-8")
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["X-Accel-Buffering"] = "no"
        return response


__all__ = ["install_streaming_routes"]
