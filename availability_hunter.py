"""Result-goal runner for NameMachine durable background searches.

Legacy large search asks for N delivered candidates. Availability Hunter instead
asks for N strict matches and treats the candidate count as a hard search budget.
The configuration is stored inside the existing search_context JSON so R2 does
not require a risky live PostgreSQL schema migration.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import select, update

from background_jobs import (
    BACKGROUND_VERIFY_WORKERS,
    _clean_name,
    _unknown_candidate,
    run_one_job as run_legacy_job,
    search_jobs,
)
from procedural_search import record_procedural_batch
from session_store import _iso, _utcnow, candidates


HUNTER_KEY = "availability_hunter"
MAX_TARGET_MATCHES = 100
STRICT_MATCH_POLICY = "claimable"


def hunter_config(job):
    context = job.get("search_context") if isinstance(job, dict) else None
    context = context if isinstance(context, dict) else {}
    raw = context.get(HUNTER_KEY)
    if not isinstance(raw, dict) or not raw.get("enabled"):
        return None
    try:
        target_matches = int(raw.get("target_matches", 0))
        max_checks = int(raw.get("max_checks", 0))
    except (TypeError, ValueError):
        return None
    if target_matches < 1 or target_matches > MAX_TARGET_MATCHES or max_checks < 1:
        return None
    return {
        "enabled": True,
        "target_matches": target_matches,
        "max_checks": max_checks,
        "match_policy": STRICT_MATCH_POLICY,
    }


def row_is_strict_match(row, required_resources):
    """A Hunter match means every required resource is directly claimable.

    Purchasable marketplace inventory and not_found observations remain useful,
    but neither satisfies the strict-free target.
    """
    if not isinstance(row, dict):
        return False
    required = [str(item) for item in (required_resources or []) if str(item)]
    if not required:
        return False
    availability = row.get("availability") if isinstance(row.get("availability"), dict) else {}
    return all(
        isinstance(availability.get(resource), dict)
        and str(availability[resource].get("status") or "unknown") == "claimable"
        for resource in required
    )


def count_persisted_matches(store, job):
    """Recompute the strict match count from durable rows for crash-safe resume."""
    engine = store.session_store._ensure_engine()
    required = list(job.get("required_resources") or job.get("resources") or [])
    with engine.connect() as conn:
        rows = conn.execute(
            select(candidates.c.row).where(
                (candidates.c.session_id == job.get("session_id"))
                & (candidates.c.run_id == job.get("run_id"))
            )
        ).scalars().all()
    return sum(1 for row in rows if row_is_strict_match(row, required))


def _persist_runtime(store, job, *, checked, matches, config):
    """Expose durable, non-secret Hunter progress through the existing job API."""
    engine = store.session_store._ensure_engine()
    preferences = dict(job.get("preferences") or {})
    preferences["_hunter_runtime"] = {
        "updated_at": _iso(_utcnow()),
        "checked": max(0, int(checked)),
        "matches": max(0, int(matches)),
        "target_matches": int(config["target_matches"]),
        "max_checks": int(config["max_checks"]),
        "match_policy": STRICT_MATCH_POLICY,
    }
    with engine.begin() as conn:
        conn.execute(
            update(search_jobs)
            .where(search_jobs.c.id == job.get("id"))
            .values(preferences=preferences, updated_at=_utcnow())
        )
    job["preferences"] = preferences
    return job


def run_availability_hunter_job(
    store,
    worker_id,
    generate_batch,
    verify_candidate,
    *,
    verify_workers=BACKGROUND_VERIFY_WORKERS,
    should_stop=None,
):
    """Execute one job, stopping on strict matches rather than candidate volume.

    Jobs without an Availability Hunter configuration retain the legacy runner,
    which preserves compatibility with existing sessions and clients.
    """
    job = store.claim_next(worker_id)
    if not job:
        return None

    config = hunter_config(job)
    if config is None:
        store.release_to_pending(
            job["id"],
            worker_id,
            int(job.get("attempted_batches") or 0),
            int(job.get("delivered_count") or 0),
        )
        return run_legacy_job(
            store,
            worker_id,
            generate_batch,
            verify_candidate,
            verify_workers=verify_workers,
            should_stop=should_stop,
        )

    attempted = int(job.get("attempted_batches") or 0)
    checked = int(job.get("delivered_count") or 0)
    max_batches = int(job.get("max_batches") or 0)
    batch_size = int(job.get("batch_size") or 1)
    max_checks = min(int(config["max_checks"]), int(job.get("target_count") or config["max_checks"]))
    target_matches = int(config["target_matches"])
    resources = list(job.get("resources") or [])
    matches = count_persisted_matches(store, job)
    _persist_runtime(store, job, checked=checked, matches=matches, config=config)

    try:
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
            generated = generate_batch(job, count, context) or []

            candidates_to_verify = []
            seen = set()
            for raw in generated:
                if not isinstance(raw, dict):
                    continue
                name = _clean_name(raw.get("name"))
                key = name.lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                candidate = dict(raw)
                candidate["name"] = name
                candidates_to_verify.append(candidate)

            verified_rows = []
            if candidates_to_verify:
                workers = max(1, min(int(verify_workers), len(candidates_to_verify), 8))
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="hunter-verify") as executor:
                    futures = {
                        executor.submit(verify_candidate, job, candidate): candidate
                        for candidate in candidates_to_verify
                    }
                    for future in as_completed(futures):
                        candidate = futures[future]
                        try:
                            row = future.result()
                        except Exception as error:
                            row = _unknown_candidate(candidate, resources, error)
                        if isinstance(row, dict) and row.get("name"):
                            verified_rows.append(row)

            inserted = store.append_candidates(job["id"], verified_rows, attempted)
            checked += inserted
            # Procedural search learns from actual provider verdicts, never from
            # guessed generation quality. This state is separate from taste feedback.
            record_procedural_batch(store, job, verified_rows)
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
    except Exception as error:
        return store.fail(job["id"], worker_id, error, attempted, checked)


__all__ = [
    "HUNTER_KEY",
    "MAX_TARGET_MATCHES",
    "STRICT_MATCH_POLICY",
    "count_persisted_matches",
    "hunter_config",
    "row_is_strict_match",
    "run_availability_hunter_job",
]
