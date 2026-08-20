"""Admission control for expensive durable background searches.

A capability token authorizes a session, but it is not a spending quota. This
module places explicit queue and check-budget limits in front of SearchJobStore so
a browser cannot create an unbounded amount of AI/provider work. The admission
lock serializes creation inside the canonical threaded web process; database
counts remain the source of truth and make the policy auditable.
"""
from __future__ import annotations

from datetime import timedelta
import os
import threading

from sqlalchemy import case, func, select

from background_jobs import ACTIVE_STATES, search_jobs
from session_store import SessionStore, _utcnow


def _bounded_env(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


MAX_ACTIVE_JOBS_PER_SESSION = _bounded_env(
    "BACKGROUND_MAX_ACTIVE_JOBS_PER_SESSION", 2, 1, 8
)
MAX_PENDING_JOBS_PER_SESSION = _bounded_env(
    "BACKGROUND_MAX_PENDING_JOBS_PER_SESSION", 1, 1, 4
)
MAX_GLOBAL_ACTIVE_JOBS = _bounded_env(
    "BACKGROUND_MAX_GLOBAL_ACTIVE_JOBS", 100, 10, 5000
)
MAX_SESSION_24H_CHECKS = _bounded_env(
    "BACKGROUND_MAX_SESSION_24H_CHECKS", 40_000, 1_000, 500_000
)

_ADMISSION_LOCK = threading.Lock()


class BackgroundJobLimitError(RuntimeError):
    def __init__(self, code, message, *, http_status=429, retry_after=60, details=None):
        super().__init__(message)
        self.code = str(code)
        self.http_status = int(http_status)
        self.retry_after = max(1, int(retry_after))
        self.details = details if isinstance(details, dict) else {}


def admission_diagnostics():
    return {
        "enabled": True,
        "max_active_jobs_per_session": MAX_ACTIVE_JOBS_PER_SESSION,
        "max_pending_jobs_per_session": MAX_PENDING_JOBS_PER_SESSION,
        "max_global_active_jobs": MAX_GLOBAL_ACTIVE_JOBS,
        "max_session_24h_checks": MAX_SESSION_24H_CHECKS,
        "budget_window_hours": 24,
        "pending_budget_reserved": True,
        "terminal_budget_uses_delivered_count": True,
    }


def evaluate_admission(*, session_active, session_pending, global_active, used_24h, requested_checks):
    """Pure policy evaluation used by both the API path and regression tests."""
    session_active = max(0, int(session_active))
    session_pending = max(0, int(session_pending))
    global_active = max(0, int(global_active))
    used_24h = max(0, int(used_24h))
    requested_checks = max(0, int(requested_checks))

    if session_pending >= MAX_PENDING_JOBS_PER_SESSION:
        raise BackgroundJobLimitError(
            "pending_job_limit",
            "This session already has the maximum number of queued background searches.",
            details={"limit": MAX_PENDING_JOBS_PER_SESSION},
        )
    if session_active >= MAX_ACTIVE_JOBS_PER_SESSION:
        raise BackgroundJobLimitError(
            "active_job_limit",
            "This session already has the maximum number of active background searches.",
            details={"limit": MAX_ACTIVE_JOBS_PER_SESSION},
        )
    if used_24h + requested_checks > MAX_SESSION_24H_CHECKS:
        raise BackgroundJobLimitError(
            "daily_check_budget",
            "This session has reached its rolling 24-hour background-check budget.",
            retry_after=3600,
            details={
                "limit": MAX_SESSION_24H_CHECKS,
                "used": used_24h,
                "requested": requested_checks,
            },
        )
    if global_active >= MAX_GLOBAL_ACTIVE_JOBS:
        raise BackgroundJobLimitError(
            "global_queue_capacity",
            "Background search is temporarily at capacity. Please retry later.",
            http_status=503,
            retry_after=60,
            details={"limit": MAX_GLOBAL_ACTIVE_JOBS},
        )


def _counts(conn, session_id, now):
    session_active = int(
        conn.execute(
            select(func.count()).select_from(search_jobs).where(
                (search_jobs.c.session_id == session_id)
                & search_jobs.c.state.in_(ACTIVE_STATES)
            )
        ).scalar_one()
    )
    session_pending = int(
        conn.execute(
            select(func.count()).select_from(search_jobs).where(
                (search_jobs.c.session_id == session_id)
                & (search_jobs.c.state == "pending")
            )
        ).scalar_one()
    )
    global_active = int(
        conn.execute(
            select(func.count()).select_from(search_jobs).where(
                search_jobs.c.state.in_(ACTIVE_STATES)
            )
        ).scalar_one()
    )
    cutoff = now - timedelta(hours=24)
    reserved_or_delivered = case(
        (search_jobs.c.state.in_(ACTIVE_STATES), search_jobs.c.target_count),
        else_=search_jobs.c.delivered_count,
    )
    used_24h = int(
        conn.execute(
            select(func.coalesce(func.sum(reserved_or_delivered), 0)).where(
                (search_jobs.c.session_id == session_id)
                & (search_jobs.c.created_at >= cutoff)
            )
        ).scalar_one()
        or 0
    )
    return {
        "session_active": session_active,
        "session_pending": session_pending,
        "global_active": global_active,
        "used_24h": used_24h,
    }


def admit_and_enqueue(job_store, session_id, token, payload):
    """Authorize, evaluate current durable usage, then enqueue under one process lock.

    The canonical Railway web runtime is one gthread Gunicorn process, so this lock
    closes the concurrent-request race in production. The durable SQL counts are
    still evaluated on every request rather than trusting browser state.
    """
    requested = max(1, int(payload.get("target_count") or 1))
    with _ADMISSION_LOCK:
        engine = job_store._engine()
        now = _utcnow()
        with engine.connect() as conn:
            if not SessionStore._authorized(conn, session_id, token):
                return None
            counts = _counts(conn, session_id, now)
        evaluate_admission(requested_checks=requested, **counts)
        return job_store.enqueue(session_id, token, payload)


__all__ = [
    "BackgroundJobLimitError",
    "MAX_ACTIVE_JOBS_PER_SESSION",
    "MAX_GLOBAL_ACTIVE_JOBS",
    "MAX_PENDING_JOBS_PER_SESSION",
    "MAX_SESSION_24H_CHECKS",
    "admission_diagnostics",
    "admit_and_enqueue",
    "evaluate_admission",
]
