"""True-live durable background runner.

Generated candidates are persisted before network verification, so the browser can
show a real name in `checking` state immediately. Each verifier completion is then
persisted one-by-one and published through the durable lifecycle event stream.
The final result-goal semantics remain identical to Availability Hunter: only a
final row counts as checked/delivered, and only direct `claimable` results satisfy
a strict-free target.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from availability_hunter import (
    STRICT_MATCH_POLICY,
    _persist_runtime,
    count_persisted_matches,
    hunter_config,
)
from background_jobs import BACKGROUND_VERIFY_WORKERS, _clean_name, _unknown_candidate
from durable_candidate_events import LIVE_CANDIDATES
from procedural_search import record_procedural_batch


def _generated_candidates(rows):
    output = []
    seen = set()
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        name = _clean_name(raw.get("name"))
        key = name.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        row = dict(raw)
        row["name"] = name
        output.append(row)
    return output


def _verify_and_finalize(
    store,
    job,
    staged,
    batch_number,
    verify_candidate,
    verify_workers,
):
    """Verify staged rows concurrently but persist completions one at a time."""
    if not staged:
        return []
    resources = list(job.get("resources") or [])
    workers = max(1, min(int(verify_workers), len(staged), 8))
    completed = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="live-background-verify") as executor:
        futures = {
            executor.submit(verify_candidate, job, candidate): candidate
            for candidate in staged
        }
        for future in as_completed(futures):
            candidate = futures[future]
            try:
                row = future.result()
            except Exception as error:
                row = _unknown_candidate(candidate, resources, error)
            if not isinstance(row, dict) or not row.get("name"):
                continue
            finalized = LIVE_CANDIDATES.finalize_candidate(job, row, batch_number)
            if finalized:
                completed.append(finalized)
    return completed


def _recover_pending(
    store,
    job,
    verify_candidate,
    verify_workers,
):
    pending = LIVE_CANDIDATES.pending_for_job(job, limit=100)
    if not pending:
        return [], 0
    batch_number = max(
        [int(row.get("batch_number") or 0) for row in pending] or [int(job.get("attempted_batches") or 0)]
    )
    completed = _verify_and_finalize(
        store,
        job,
        pending,
        max(1, batch_number),
        verify_candidate,
        verify_workers,
    )
    return completed, batch_number


def _run_legacy(
    store,
    job,
    worker_id,
    generate_batch,
    verify_candidate,
    *,
    verify_workers,
    should_stop,
):
    attempted = int(job.get("attempted_batches") or 0)
    delivered = int(job.get("delivered_count") or 0)
    target = int(job["target_count"])
    max_batches = int(job["max_batches"])
    batch_size = int(job["batch_size"])

    recovered, recovered_batch = _recover_pending(
        store, job, verify_candidate, verify_workers
    )
    if recovered:
        attempted = max(attempted, recovered_batch)
        delivered += len(recovered)
        record_procedural_batch(store, job, recovered)
        job = store.checkpoint(job["id"], worker_id, attempted, delivered) or job

    while delivered < target and attempted < max_batches:
        if should_stop and should_stop():
            return store.release_to_pending(job["id"], worker_id, attempted, delivered)
        if store.is_cancel_requested(job["id"]):
            return store.finish(
                job["id"], worker_id, "cancelled", "user_cancelled", attempted, delivered
            )

        attempted += 1
        count = min(batch_size, target - delivered)
        context = dict(job.get("generation_context") or {})
        context["batch_number"] = min(5, attempted)
        context["exclude_names"] = store.recent_names(job["session_id"], 100)
        generated = _generated_candidates(generate_batch(job, count, context) or [])
        staged = LIVE_CANDIDATES.stage_candidates(job, generated, attempted)
        completed = _verify_and_finalize(
            store,
            job,
            staged,
            attempted,
            verify_candidate,
            verify_workers,
        )
        delivered += len(completed)
        record_procedural_batch(store, job, completed)
        job = store.checkpoint(job["id"], worker_id, attempted, delivered) or job

    reason = "target_reached" if delivered >= target else "max_batches"
    return store.finish(job["id"], worker_id, "completed", reason, attempted, delivered)


def _run_hunter(
    store,
    job,
    config,
    worker_id,
    generate_batch,
    verify_candidate,
    *,
    verify_workers,
    should_stop,
):
    attempted = int(job.get("attempted_batches") or 0)
    checked = int(job.get("delivered_count") or 0)
    max_batches = int(job.get("max_batches") or 0)
    batch_size = int(job.get("batch_size") or 1)
    max_checks = min(
        int(config["max_checks"]),
        int(job.get("target_count") or config["max_checks"]),
    )
    target_matches = int(config["target_matches"])
    matches = count_persisted_matches(store, job)
    _persist_runtime(store, job, checked=checked, matches=matches, config=config)

    recovered, recovered_batch = _recover_pending(
        store, job, verify_candidate, verify_workers
    )
    if recovered:
        attempted = max(attempted, recovered_batch)
        checked += len(recovered)
        record_procedural_batch(store, job, recovered)
        matches = count_persisted_matches(store, job)
        _persist_runtime(store, job, checked=checked, matches=matches, config=config)
        job = store.checkpoint(job["id"], worker_id, attempted, checked) or job

    if matches >= target_matches:
        return store.finish(
            job["id"], worker_id, "completed", "target_matches_reached", attempted, checked
        )

    while checked < max_checks and attempted < max_batches:
        if should_stop and should_stop():
            return store.release_to_pending(job["id"], worker_id, attempted, checked)
        if store.is_cancel_requested(job["id"]):
            return store.finish(
                job["id"], worker_id, "cancelled", "user_cancelled", attempted, checked
            )

        attempted += 1
        count = min(batch_size, max_checks - checked)
        context = dict(job.get("generation_context") or {})
        context["batch_number"] = min(5, attempted)
        context["exclude_names"] = store.recent_names(job["session_id"], 100)
        context["availability_hunter"] = {
            "target_matches": target_matches,
            "current_matches": matches,
            "max_checks": max_checks,
            "checked": checked,
            "match_policy": STRICT_MATCH_POLICY,
        }
        generated = _generated_candidates(generate_batch(job, count, context) or [])
        staged = LIVE_CANDIDATES.stage_candidates(job, generated, attempted)
        completed = _verify_and_finalize(
            store,
            job,
            staged,
            attempted,
            verify_candidate,
            verify_workers,
        )
        checked += len(completed)
        record_procedural_batch(store, job, completed)
        matches = count_persisted_matches(store, job)
        _persist_runtime(store, job, checked=checked, matches=matches, config=config)
        job = store.checkpoint(job["id"], worker_id, attempted, checked) or job

        if matches >= target_matches:
            return store.finish(
                job["id"], worker_id, "completed", "target_matches_reached", attempted, checked
            )

    return store.finish(
        job["id"], worker_id, "completed", "search_budget_exhausted", attempted, checked
    )


def run_live_background_job(
    store,
    worker_id,
    generate_batch,
    verify_candidate,
    *,
    verify_workers=BACKGROUND_VERIFY_WORKERS,
    should_stop=None,
):
    """Claim and execute one job with durable candidate lifecycle events."""
    job = store.claim_next(worker_id)
    if not job:
        return None
    try:
        config = hunter_config(job)
        if config is None:
            return _run_legacy(
                store,
                job,
                worker_id,
                generate_batch,
                verify_candidate,
                verify_workers=verify_workers,
                should_stop=should_stop,
            )
        return _run_hunter(
            store,
            job,
            config,
            worker_id,
            generate_batch,
            verify_candidate,
            verify_workers=verify_workers,
            should_stop=should_stop,
        )
    except Exception as error:
        attempted = int(job.get("attempted_batches") or 0)
        delivered = int(job.get("delivered_count") or 0)
        return store.fail(job["id"], worker_id, error, attempted, delivered)


__all__ = ["run_live_background_job"]
