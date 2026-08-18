"""NameMachine durable background search worker.

Run this as a separate process/service, for example `python search_worker.py`.
It never needs a user's plaintext session token: authorization is performed when
the web API enqueues the job, while the worker is a trusted server-side process.
"""

from __future__ import annotations

import os
import signal
import socket
import threading

from sqlalchemy import select, update

from telegram_integration import install


install()

import app as app_module  # noqa: E402
from availability_hunter import run_availability_hunter_job  # noqa: E402
from availability_v2 import check_all as check_all_v2  # noqa: E402
from background_jobs import JOB_STORE, search_jobs  # noqa: E402
from session_store import _iso, _utcnow, candidates, feedback, sessions  # noqa: E402
from streaming_search import _generate_candidates  # noqa: E402
from worker_heartbeat import beat, remove  # noqa: E402


STOP = threading.Event()
CONFLICT_STATUSES = {"taken", "reserved", "invalid"}
POSITIVE_HINT_STATUSES = {"claimable", "purchasable", "not_found"}


def _bounded_float(name, default, minimum, maximum):
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _worker_id():
    configured = str(os.environ.get("NAMEMACHINE_WORKER_ID") or "").strip()
    if configured:
        return configured[:96]
    return f"{socket.gethostname()}-{os.getpid()}"[:96]


def _clean_feedback_vote(value):
    try:
        vote = int(value)
    except (TypeError, ValueError):
        vote = 0
    return 1 if vote > 0 else -1 if vote < 0 else 0


def _row_has_hard_conflict(row):
    if str(row.get("bundle_state") or "") == "conflict":
        return True
    availability = row.get("availability") if isinstance(row.get("availability"), dict) else {}
    return any(
        str(payload.get("status") or "unknown") in CONFLICT_STATUSES
        for payload in availability.values()
        if isinstance(payload, dict)
    )


def _row_is_low_collision_hint(row):
    if _row_has_hard_conflict(row):
        return False
    state = str(row.get("bundle_state") or "")
    if state in {"confirmed", "promising"}:
        return True
    availability = row.get("availability") if isinstance(row.get("availability"), dict) else {}
    statuses = {
        str(payload.get("status") or "unknown")
        for payload in availability.values()
        if isinstance(payload, dict)
    }
    return bool(statuses & POSITIVE_HINT_STATUSES)


def _runtime_generation_state(job, generation_context):
    """Refresh user feedback and verification lessons before every AI batch.

    Background jobs are long-lived. The launch-time preference snapshot is therefore
    not enough: likes, dislikes, comments, shortlist changes and direction anchors
    made while the job is running must affect the next batch. Verification outcomes
    from prior batches also become conflict/success examples for the generator.
    """
    base_preferences = dict(job.get("preferences") or {})
    context = dict(generation_context or {})
    engine = JOB_STORE.session_store._ensure_engine()
    session_id = job.get("session_id")

    with engine.connect() as conn:
        session_row = conn.execute(
            select(sessions.c.shortlist, sessions.c.direction_anchors).where(sessions.c.id == session_id)
        ).mappings().one_or_none()
        feedback_rows = conn.execute(
            select(feedback.c.name_key, feedback.c.payload, feedback.c.updated_at)
            .where(feedback.c.session_id == session_id)
            .order_by(feedback.c.updated_at.asc())
        ).mappings().all()
        recent_rows = conn.execute(
            select(candidates.c.name_key, candidates.c.row)
            .where(candidates.c.session_id == session_id)
            .order_by(candidates.c.received_seq.desc(), candidates.c.updated_at.desc())
            .limit(160)
        ).mappings().all()

    recent = [dict(item["row"] or {}) for item in recent_rows if isinstance(item.get("row"), dict)]
    by_key = {
        str(item.get("name_key") or "").lower(): dict(item.get("row") or {})
        for item in recent_rows
        if isinstance(item.get("row"), dict)
    }

    feedback_items = []
    liked = []
    disliked = []
    latest_feedback_at = None
    for item in feedback_rows:
        payload = dict(item.get("payload") or {})
        key = str(item.get("name_key") or "").lower()
        candidate = by_key.get(key, {})
        display_name = str(candidate.get("name") or key)
        vote = _clean_feedback_vote(payload.get("vote"))
        comment = " ".join(str(payload.get("comment") or "").split())[:300]
        family = str(candidate.get("family") or payload.get("family") or "unknown")[:30]
        feedback_items.append({
            "name": display_name,
            "vote": vote,
            "comment": comment,
            "family": family,
        })
        if vote > 0:
            liked.append(display_name)
        elif vote < 0:
            disliked.append(display_name)
        if item.get("updated_at"):
            latest_feedback_at = _iso(item["updated_at"])

    shortlist = list(session_row.get("shortlist") or []) if session_row else []
    anchors = list(session_row.get("direction_anchors") or []) if session_row else []

    preferences = dict(base_preferences)
    preferences["liked"] = liked[-20:]
    preferences["disliked"] = disliked[-20:]
    preferences["feedback"] = feedback_items[-80:]
    preferences["direction_anchors"] = anchors[-20:]
    preferences["shortlist"] = shortlist[-20:]

    recent_names = [str(row.get("name") or "") for row in recent if str(row.get("name") or "")]
    conflict_names = [str(row.get("name") or "") for row in recent if _row_has_hard_conflict(row)]
    opportunity_names = [
        str(row.get("name") or "")
        for row in recent
        if str(row.get("name") or "") and _row_is_low_collision_hint(row)
    ]
    directional = []
    seen = set()
    for name in [*anchors, *shortlist, *liked, *opportunity_names]:
        key = str(name).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        directional.append(str(name).strip())

    context["exclude_names"] = recent_names[:100]
    context["conflict_names"] = conflict_names[:40]
    context["successful_names"] = directional[:20]

    runtime = {
        "applied_at": _iso(_utcnow()),
        "applied_batch": int(job.get("attempted_batches") or 0) + 1,
        "feedback_count": len(feedback_items),
        "liked_count": len(liked),
        "disliked_count": len(disliked),
        "latest_feedback_at": latest_feedback_at,
        "conflict_examples": len(context["conflict_names"]),
        "opportunity_examples": len(context["successful_names"]),
    }
    preferences["_runtime"] = runtime

    # Persist the worker-read snapshot so the authenticated job API can prove to
    # the browser/report when feedback was actually consumed by the worker.
    with engine.begin() as conn:
        conn.execute(
            update(search_jobs)
            .where(search_jobs.c.id == job.get("id"))
            .values(preferences=preferences, updated_at=_utcnow())
        )

    return preferences, context, runtime


def generate_batch(job, count, generation_context):
    brief = job.get("prompt") or ""
    search_context = dict(job.get("search_context") or {})
    resources = job.get("resources") or []
    try:
        preferences, generation_context, runtime = _runtime_generation_state(job, generation_context)
    except Exception as error:
        print(f"NameMachine runtime feedback refresh failed: {type(error).__name__}", flush=True)
        preferences = job.get("preferences") or {}
        runtime = {}

    if runtime.get("conflict_examples"):
        extra = (
            "Попередні перевірки показують зайнятий цифровий простір. "
            "Підвищуй унікальність, змінюй корені й фонетичні структури, а не роби дрібні мутації зайнятих назв."
        )
        existing_guidance = str(search_context.get("guidance") or "").strip()
        search_context["guidance"] = " ".join(part for part in [existing_guidance, extra] if part)[:500]

    if os.environ.get("OPENAI_API_KEY"):
        brief, search_context, _intelligence = app_module.apply_prompt_intelligence(
            brief,
            resources,
            search_context,
        )
    data = {"preferences": preferences}
    return _generate_candidates(
        app_module,
        brief,
        count,
        data,
        job.get("brand_dna"),
        search_context,
        generation_context,
    )


def verify_candidate(job, candidate):
    result = dict(candidate or {})
    name = str(result.get("name") or "").strip()
    if not name:
        raise ValueError("Candidate has no name")
    checked = check_all_v2(name, resources=job.get("resources") or [])
    result.update(checked)
    result.update(
        app_module.classify_identity_bundle(
            result.get("availability"),
            job.get("required_resources") or job.get("resources") or [],
        )
    )
    result["trademark"] = app_module.trademark_links(name)
    result["checked"] = True
    return result


def _request_stop(*_args):
    STOP.set()


def _heartbeat_loop(worker_id):
    interval = _bounded_float("BACKGROUND_WORKER_HEARTBEAT_SECONDS", 20.0, 5.0, 60.0)
    while not STOP.is_set():
        try:
            beat(JOB_STORE.session_store, worker_id)
        except Exception as error:
            print(f"NameMachine worker heartbeat failed: {type(error).__name__}", flush=True)
        STOP.wait(interval)


def main():
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    if not JOB_STORE.configured:
        print("NameMachine background worker: database is not configured.", flush=True)
        return 2
    if not JOB_STORE.session_store.ensure_ready():
        print("NameMachine background worker: database is not reachable.", flush=True)
        return 3

    worker_id = _worker_id()
    idle_seconds = _bounded_float("BACKGROUND_WORKER_IDLE_SECONDS", 2.0, 0.25, 30.0)
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(worker_id,),
        name="namemachine-worker-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()
    print(f"NameMachine background worker started: {worker_id}", flush=True)

    try:
        while not STOP.is_set():
            result = run_availability_hunter_job(
                JOB_STORE,
                worker_id,
                generate_batch,
                verify_candidate,
                should_stop=STOP.is_set,
            )
            if result is None:
                STOP.wait(idle_seconds)
            else:
                hunter = (result.get("preferences") or {}).get("_hunter_runtime") or {}
                suffix = (
                    f" matches={hunter.get('matches', 0)}/{hunter.get('target_matches', 0)}"
                    if hunter else ""
                )
                print(
                    "background job",
                    result.get("id"),
                    result.get("state"),
                    f"{result.get('delivered_count', 0)}/{result.get('target_count', 0)}{suffix}",
                    result.get("stop_reason") or "",
                    flush=True,
                )
    finally:
        STOP.set()
        heartbeat_thread.join(timeout=2.0)
        try:
            remove(JOB_STORE.session_store, worker_id)
        except Exception:
            pass

    print("NameMachine background worker stopped.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
