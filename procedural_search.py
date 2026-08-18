"""Durable procedural search planning for NameMachine.

The planner deliberately explores one semantic root at a time. Within each root
it walks a bounded sequence of transformation strategies and advances only after
that strategy has gathered enough real verification evidence. This replaces the
old implicit "batch 1..5" notion with an auditable search position.
"""
from __future__ import annotations

import re

from sqlalchemy import update

from background_jobs import search_jobs
from candidate_funnel import lexical_seeds
from session_store import _iso, _utcnow


PROCEDURAL_KEY = "procedural_search"
RUNTIME_KEY = "_procedural_runtime"
STRATEGIES = (
    "direct",
    "compression",
    "phonetic",
    "blend",
    "compound",
)
STRATEGY_RULES = {
    "direct": "Stay visibly anchored to the focus root; use clean, obvious brandable developments rather than unrelated abstractions.",
    "compression": "Compress and shorten the focus root while preserving recognizability and natural pronunciation.",
    "phonetic": "Explore pronounceable phonetic developments of the focus root; do not merely swap one letter.",
    "blend": "Blend the focus root with one semantically related supporting root, while the focus root remains the dominant anchor.",
    "compound": "Build concise semantic compounds around the focus root; avoid unrelated metaphor jumps.",
}
MIN_STRATEGY_CHECKS = 20
MAX_STRATEGY_CHECKS = 40
HIGH_COLLISION_RATE = 0.80
MAX_ROOTS = 16


def _clean_root(value):
    return re.sub(r"[^a-z]", "", str(value or "").lower())[:20]


def clean_roots(values):
    output = []
    seen = set()
    for value in values or []:
        root = _clean_root(value)
        if len(root) < 3 or root in seen:
            continue
        seen.add(root)
        output.append(root)
        if len(output) >= MAX_ROOTS:
            break
    return output


def procedural_config(job):
    context = job.get("search_context") if isinstance(job, dict) else None
    context = context if isinstance(context, dict) else {}
    raw = context.get(PROCEDURAL_KEY)
    if not isinstance(raw, dict) or not raw.get("enabled"):
        return None
    return {"enabled": True, "strategy": "procedural"}


def _new_runtime(roots):
    now = _iso(_utcnow())
    return {
        "enabled": True,
        "roots": list(roots),
        "root_index": 0,
        "strategy_index": 0,
        "current_root": roots[0] if roots else "",
        "current_strategy": STRATEGIES[0],
        "strategy_checked": 0,
        "strategy_conflicts": 0,
        "strategy_matches": 0,
        "root_checked": 0,
        "root_conflicts": 0,
        "root_matches": 0,
        "total_checked": 0,
        "visited": [],
        "updated_at": now,
        "exhausted": not bool(roots),
    }


def _runtime_from_job(job, roots):
    preferences = job.get("preferences") if isinstance(job, dict) else None
    preferences = preferences if isinstance(preferences, dict) else {}
    existing = preferences.get(RUNTIME_KEY)
    if not isinstance(existing, dict):
        return _new_runtime(roots)

    runtime = dict(existing)
    existing_roots = clean_roots(runtime.get("roots"))
    if not existing_roots:
        existing_roots = list(roots)
    runtime["roots"] = existing_roots
    root_index = max(0, min(int(runtime.get("root_index") or 0), max(0, len(existing_roots) - 1)))
    strategy_index = max(0, min(int(runtime.get("strategy_index") or 0), len(STRATEGIES) - 1))
    runtime["root_index"] = root_index
    runtime["strategy_index"] = strategy_index
    runtime["current_root"] = existing_roots[root_index] if existing_roots else ""
    runtime["current_strategy"] = STRATEGIES[strategy_index]
    runtime["exhausted"] = bool(runtime.get("exhausted")) or not bool(existing_roots)
    return runtime


def _persist(store, job, runtime):
    preferences = dict(job.get("preferences") or {})
    runtime = dict(runtime)
    runtime["updated_at"] = _iso(_utcnow())
    preferences[RUNTIME_KEY] = runtime
    engine = store.session_store._ensure_engine()
    with engine.begin() as conn:
        conn.execute(
            update(search_jobs)
            .where(search_jobs.c.id == job.get("id"))
            .values(preferences=preferences, updated_at=_utcnow())
        )
    job["preferences"] = preferences
    return runtime


def roots_from_intelligence(job, intelligence=None):
    roots = clean_roots(
        intelligence.get("naming_roots") if isinstance(intelligence, dict) else []
    )
    if len(roots) >= 2:
        return roots
    fallback = lexical_seeds(job.get("prompt") or "", job.get("brand_dna"), limit=MAX_ROOTS)
    combined = clean_roots([*roots, *fallback])
    return combined


def prepare_procedural_context(store, job, generation_context, intelligence=None):
    """Return generation context pinned to one durable root/strategy position."""
    if procedural_config(job) is None:
        return dict(generation_context or {}), None

    roots = roots_from_intelligence(job, intelligence)
    runtime = _runtime_from_job(job, roots)
    if runtime.get("exhausted"):
        _persist(store, job, runtime)
        return dict(generation_context or {}), runtime

    runtime = _persist(store, job, runtime)
    context = dict(generation_context or {})
    context["procedural"] = {
        "enabled": True,
        "focus_root": runtime["current_root"],
        "strategy": runtime["current_strategy"],
        "strategy_rule": STRATEGY_RULES[runtime["current_strategy"]],
        "supporting_roots": [root for root in runtime["roots"] if root != runtime["current_root"]][:6],
        "root_index": runtime["root_index"],
        "root_count": len(runtime["roots"]),
        "strategy_index": runtime["strategy_index"],
        "strategy_count": len(STRATEGIES),
    }
    return context, runtime


def _is_match(row, required_resources):
    availability = row.get("availability") if isinstance(row, dict) and isinstance(row.get("availability"), dict) else {}
    required = list(required_resources or [])
    return bool(required) and all(
        isinstance(availability.get(resource), dict)
        and str(availability[resource].get("status") or "unknown") == "claimable"
        for resource in required
    )


def _is_conflict(row, required_resources):
    availability = row.get("availability") if isinstance(row, dict) and isinstance(row.get("availability"), dict) else {}
    return any(
        isinstance(availability.get(resource), dict)
        and str(availability[resource].get("status") or "unknown") in {"taken", "reserved", "invalid"}
        for resource in required_resources or []
    )


def _advance(runtime, reason):
    visited = list(runtime.get("visited") or [])
    checked = int(runtime.get("strategy_checked") or 0)
    conflicts = int(runtime.get("strategy_conflicts") or 0)
    matches = int(runtime.get("strategy_matches") or 0)
    visited.append({
        "root": runtime.get("current_root") or "",
        "strategy": runtime.get("current_strategy") or "",
        "checked": checked,
        "conflicts": conflicts,
        "matches": matches,
        "collision_rate": round(conflicts / checked, 3) if checked else 0.0,
        "advance_reason": reason,
    })
    runtime["visited"] = visited[-80:]

    strategy_index = int(runtime.get("strategy_index") or 0) + 1
    root_index = int(runtime.get("root_index") or 0)
    if strategy_index >= len(STRATEGIES):
        strategy_index = 0
        root_index += 1
        runtime["root_checked"] = 0
        runtime["root_conflicts"] = 0
        runtime["root_matches"] = 0

    roots = runtime.get("roots") or []
    if root_index >= len(roots):
        runtime["exhausted"] = True
        runtime["current_root"] = ""
        runtime["current_strategy"] = ""
    else:
        runtime["root_index"] = root_index
        runtime["strategy_index"] = strategy_index
        runtime["current_root"] = roots[root_index]
        runtime["current_strategy"] = STRATEGIES[strategy_index]

    runtime["strategy_checked"] = 0
    runtime["strategy_conflicts"] = 0
    runtime["strategy_matches"] = 0
    return runtime


def record_procedural_batch(store, job, rows):
    """Update planner yield statistics from actual verifier outcomes.

    High-collision strategies are abandoned after the minimum sample; productive
    strategies receive a larger sample. Every strategy is still bounded, so a
    root eventually exhausts and the planner advances to the next semantic root.
    """
    if procedural_config(job) is None:
        return None
    roots = roots_from_intelligence(job)
    runtime = _runtime_from_job(job, roots)
    if runtime.get("exhausted"):
        return _persist(store, job, runtime)

    required = list(job.get("required_resources") or job.get("resources") or [])
    usable_rows = [row for row in (rows or []) if isinstance(row, dict) and row.get("name")]
    checked = len(usable_rows)
    conflicts = sum(1 for row in usable_rows if _is_conflict(row, required))
    matches = sum(1 for row in usable_rows if _is_match(row, required))

    runtime["strategy_checked"] = int(runtime.get("strategy_checked") or 0) + checked
    runtime["strategy_conflicts"] = int(runtime.get("strategy_conflicts") or 0) + conflicts
    runtime["strategy_matches"] = int(runtime.get("strategy_matches") or 0) + matches
    runtime["root_checked"] = int(runtime.get("root_checked") or 0) + checked
    runtime["root_conflicts"] = int(runtime.get("root_conflicts") or 0) + conflicts
    runtime["root_matches"] = int(runtime.get("root_matches") or 0) + matches
    runtime["total_checked"] = int(runtime.get("total_checked") or 0) + checked

    strategy_checked = int(runtime["strategy_checked"])
    collision_rate = (
        int(runtime["strategy_conflicts"]) / strategy_checked
        if strategy_checked else 0.0
    )
    if strategy_checked >= MIN_STRATEGY_CHECKS and collision_rate >= HIGH_COLLISION_RATE:
        runtime = _advance(runtime, "high_collision")
    elif strategy_checked >= MAX_STRATEGY_CHECKS:
        runtime = _advance(runtime, "strategy_budget")

    return _persist(store, job, runtime)


__all__ = [
    "HIGH_COLLISION_RATE",
    "MAX_STRATEGY_CHECKS",
    "MIN_STRATEGY_CHECKS",
    "PROCEDURAL_KEY",
    "RUNTIME_KEY",
    "STRATEGIES",
    "prepare_procedural_context",
    "procedural_config",
    "record_procedural_batch",
    "roots_from_intelligence",
]
