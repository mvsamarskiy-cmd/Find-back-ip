"""Result-goal runner for NameMachine durable background searches.

Hunter keeps strict-green truth separate from practical discovery goals. A job can
stop on all-resource strict claimability, on a no-conflict bundle, or when at
least one selected channel has an actionable/absence opportunity signal. None of
the looser policies rewrites ``not_found`` into ``claimable``.
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
STRICT_MATCH_POLICY = "strict_all"
MATCH_POLICIES = frozenset({"strict_all", "no_conflict", "any_opportunity"})
HARD_CONFLICT = frozenset({"taken", "reserved", "invalid"})
OPPORTUNITY = frozenset({"claimable", "purchasable", "not_found"})


def normalize_match_policy(value):
    raw = str(value or STRICT_MATCH_POLICY).strip().lower()
    aliases = {
        "claimable": "strict_all",
        "strict": "strict_all",
        "all_claimable": "strict_all",
        "promising": "no_conflict",
        "any_free_signal": "any_opportunity",
        "any_absence": "any_opportunity",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in MATCH_POLICIES else STRICT_MATCH_POLICY


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
        "match_policy": normalize_match_policy(raw.get("match_policy")),
    }


def row_matches_policy(row, required_resources, policy=STRICT_MATCH_POLICY):
    """Evaluate a discovery goal without changing any resource verdict.

    ``strict_all`` means every selected resource is directly claimable.
    ``no_conflict`` means no selected resource has a hard conflict and at least
    one selected resource has a claimable/purchasable/not_found opportunity.
    ``any_opportunity`` means at least one selected resource has such an
    opportunity, even if another selected channel is occupied.
    """
    if not isinstance(row, dict):
        return False
    required = [str(item) for item in (required_resources or []) if str(item)]
    if not required:
        return False
    availability = row.get("availability") if isinstance(row.get("availability"), dict) else {}
    statuses = [
        str((availability.get(resource) or {}).get("status") or "unknown")
        if isinstance(availability.get(resource), dict) else "unknown"
        for resource in required
    ]
    policy = normalize_match_policy(policy)
    if policy == "strict_all":
        return all(status == "claimable" for status in statuses)
    has_opportunity = any(status in OPPORTUNITY for status in statuses)
    if policy == "no_conflict":
        return has_opportunity and not any(status in HARD_CONFLICT for status in statuses)
    return has_opportunity


def row_is_strict_match(row, required_resources):
    """Backward-compatible strict matcher used by existing tests/callers."""
    return row_matches_policy(row, required_resources, "strict_all")


def count_persisted_matches(store, job, policy=None):
    """Recompute the selected match count from durable rows for crash-safe resume."""
    engine = store.session_store._ensure_engine()
    required = list(job.get("required_resources") or job.get("resources") or [])
    config = hunter_config(job) or {}
    match_policy = normalize_match_policy(policy or config.get("match_policy"))
    with engine.connect() as conn:
        rows = conn.execute(
            select(candidates.c.row).where(
                (candidates.c.session_id == job.get("session_id"))
                & (candidates.c.run_id == job.get("run_id"))
            )
        ).scalars().all()
    return sum(1 for row in rows if row_matches_policy(row, required, match_policy))


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
        "match_policy": normalize_match_policy(config.get("match_policy")),
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
    """Execute one Hunter job and stop when its configured discovery goal is met."""
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
    match_policy = normalize_match_policy(config.get("match_policy"))
    resources = list(job.get("resources") or [])
    matches = count_persisted_matches(store, job, match_policy)
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
                "match_policy": match_policy,
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
            matches = count_persisted_matches(store, job, match_policy)
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
    "HARD_CONFLICT",
    "HUNTER_KEY",
    "MATCH_POLICIES",
    "MAX_TARGET_MATCHES",
    "OPPORTUNITY",
    "STRICT_MATCH_POLICY",
    "count_persisted_matches",
    "hunter_config",
    "normalize_match_policy",
    "row_is_strict_match",
    "row_matches_policy",
    "run_availability_hunter_job",
]
