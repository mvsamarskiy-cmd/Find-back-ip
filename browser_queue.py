"""Durable queue connecting fast foreground results to Browser Intelligence.

The UI/search stream stays completely independent from browser latency. Candidate
persistence is already best-effort and asynchronous in the browser client; this
module attaches a tiny SQL queue to that persistence boundary. The background
worker then claims those rows and submits them to the existing bounded Browser
Eye runtime.

This gives foreground and long-running searches the same expensive verification
pipe without calling Playwright from the web process or blocking NDJSON output.
"""
from __future__ import annotations

from datetime import timedelta
import os
from threading import Lock
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Table,
    and_,
    or_,
    select,
    update,
)

from session_store import STORE, SessionStore, _utcnow, candidates, metadata


QUEUE_TABLE = "nm_browser_enrichment_jobs"
SOCIAL_RESOURCES = frozenset({"instagram", "telegram", "tiktok", "youtube", "facebook", "x"})
HARD_CONFLICT = frozenset({"taken", "reserved", "invalid"})
TERMINAL_STATES = frozenset({"completed", "skipped", "failed"})


def _bounded_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


BROWSER_JOB_MAX_ATTEMPTS = _bounded_int("BROWSER_JOB_MAX_ATTEMPTS", 3, 1, 8)
BROWSER_JOB_LEASE_SECONDS = _bounded_int("BROWSER_JOB_LEASE_SECONDS", 60, 15, 300)
BROWSER_QUEUE_IDLE_MS = _bounded_int("BROWSER_QUEUE_IDLE_MS", 350, 100, 5000)

browser_jobs = Table(
    QUEUE_TABLE,
    metadata,
    Column("session_id", String(36), ForeignKey("nm_sessions.id", ondelete="CASCADE"), nullable=False),
    Column("name_key", String(96), nullable=False),
    Column("id", String(36), nullable=False),
    Column("run_id", String(96), nullable=True),
    Column("state", String(24), nullable=False),
    Column("attempts", Integer, nullable=False, default=0),
    Column("worker_id", String(96), nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("last_error_type", String(96), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("session_id", "name_key"),
)


def _status(row):
    return str((row or {}).get("status") or "unknown").lower() if isinstance(row, dict) else "unknown"


def _browser_candidate(row):
    if not isinstance(row, dict) or not row.get("name") or row.get("checked") is not True:
        return False
    if str(row.get("product_mode") or "") == "generic_name":
        return False
    if str(row.get("browser_verification_state") or "") == "complete":
        return False
    availability = row.get("availability") if isinstance(row.get("availability"), dict) else {}
    if not availability:
        return False
    # Once any selected resource has a hard conflict the candidate cannot become
    # a strict recommendation. Spending browser CPU on it would slow useful work.
    if any(_status(payload) in HARD_CONFLICT for payload in availability.values() if isinstance(payload, dict)):
        return False
    return any(resource in SOCIAL_RESOURCES for resource in availability)


SERVER_BROWSER_KEYS = (
    "browser_verification",
    "browser_verification_state",
    "browser_enriched_at",
    "bundle_availability_state",
    "bundle_claimable",
    "bundle_purchasable",
    "structural_quality_score",
    "linguistic_quality_score",
    "name_quality_score",
    "user_fit_score",
    "adaptive_relevance_score",
    "identity_relevance_score",
    "availability_opportunity_score",
    "availability_evidence_confidence_score",
    "verification_coverage_score",
    "final_score",
    "availability_state",
    "ranking_model",
    "ranking_reason",
)


class BrowserJobQueue:
    def __init__(self, session_store=None):
        self.session_store = session_store or STORE
        self._table_ready = False
        self._table_lock = Lock()

    @property
    def configured(self):
        return self.session_store.configured and bool(str(os.environ.get("BROWSER_EYE_URL") or "").strip())

    def _engine(self):
        """Return the shared engine without schema introspection on every poll.

        `browser_jobs` is registered on the shared NameMachine metadata before the
        normal production store is first initialized, so SessionStore.create_all
        creates it in the usual case. The guarded `create(checkfirst=True)` is only
        a compatibility fallback for unusual import orders or isolated tests.
        """
        engine = self.session_store._ensure_engine()
        if self._table_ready:
            return engine
        with self._table_lock:
            if not self._table_ready:
                browser_jobs.create(engine, checkfirst=True)
                self._table_ready = True
        return engine

    def diagnostics(self):
        return {
            "configured": self.configured,
            "durable": True,
            "table": QUEUE_TABLE,
            "max_attempts": BROWSER_JOB_MAX_ATTEMPTS,
            "lease_seconds": BROWSER_JOB_LEASE_SECONDS,
            "foreground_stream_blocking": False,
            "enqueue_boundary": "async_candidate_persistence",
            "schema_check_hot_path": False,
        }

    @staticmethod
    def _merge_existing_browser(existing, incoming):
        """Protect server Browser Eye facts from a stale client mirror write."""
        if not isinstance(existing, dict) or not isinstance(incoming, dict):
            return incoming
        if str(existing.get("browser_verification_state") or "") != "complete":
            return incoming
        existing_run = str(existing.get("run_id") or "")
        incoming_run = str(incoming.get("run_id") or "")
        if existing_run and incoming_run and existing_run != incoming_run:
            # A genuine later run is allowed to recheck the same spelling.
            return incoming
        merged = dict(incoming)
        # Browser fusion may strengthen absence or discover occupancy, so its
        # availability snapshot and the ranking derived from it are server facts.
        if isinstance(existing.get("availability"), dict):
            merged["availability"] = existing["availability"]
        for key in SERVER_BROWSER_KEYS:
            if key in existing:
                merged[key] = existing[key]
        return merged

    def preserve_server_enrichment(self, session_id, rows):
        """Merge completed server enrichment into same-run client mirror rows."""
        rows = [dict(row) for row in (rows or []) if isinstance(row, dict)]
        if not rows or not self.session_store.configured:
            return rows
        keys = [str(row.get("name") or "").strip().lower()[:96] for row in rows]
        keys = [key for key in keys if key]
        if not keys:
            return rows
        engine = self._engine()
        with engine.connect() as conn:
            existing_rows = conn.execute(
                select(candidates.c.name_key, candidates.c.row).where(
                    (candidates.c.session_id == session_id) & candidates.c.name_key.in_(keys)
                )
            ).mappings().all()
        existing = {
            str(item["name_key"]): dict(item["row"] or {})
            for item in existing_rows
            if isinstance(item.get("row"), dict)
        }
        return [
            self._merge_existing_browser(existing.get(str(row.get("name") or "").lower()), row)
            for row in rows
        ]

    def enqueue_rows(self, session_id, rows):
        if not self.configured:
            return 0
        eligible = [dict(row) for row in (rows or []) if _browser_candidate(row)]
        if not eligible:
            return 0
        engine = self._engine()
        now = _utcnow()
        accepted = 0
        with engine.begin() as conn:
            for row in eligible:
                name_key = str(row.get("name") or "").strip().lower()[:96]
                run_id = str(row.get("run_id") or "")[:96] or None
                if not name_key:
                    continue
                existing = conn.execute(
                    select(browser_jobs.c.run_id, browser_jobs.c.state).where(
                        (browser_jobs.c.session_id == session_id)
                        & (browser_jobs.c.name_key == name_key)
                    )
                ).mappings().one_or_none()
                if existing and str(existing.get("run_id") or "") == str(run_id or ""):
                    if str(existing.get("state") or "") in {"pending", "running", "completed"}:
                        continue
                values = {
                    "session_id": session_id,
                    "name_key": name_key,
                    "id": str(uuid.uuid4()),
                    "run_id": run_id,
                    "state": "pending",
                    "attempts": 0,
                    "worker_id": None,
                    "lease_expires_at": None,
                    "last_error_type": None,
                    "created_at": now,
                    "updated_at": now,
                }
                SessionStore._upsert(
                    conn,
                    browser_jobs,
                    (browser_jobs.c.session_id == session_id) & (browser_jobs.c.name_key == name_key),
                    values,
                )
                accepted += 1
        return accepted

    def claim_next(self, worker_id):
        if not self.configured:
            return None
        engine = self._engine()
        now = _utcnow()
        lease = now + timedelta(seconds=BROWSER_JOB_LEASE_SECONDS)
        for _ in range(8):
            with engine.begin() as conn:
                stmt = (
                    select(browser_jobs)
                    .where(
                        or_(
                            browser_jobs.c.state == "pending",
                            and_(
                                browser_jobs.c.state == "running",
                                browser_jobs.c.lease_expires_at.is_not(None),
                                browser_jobs.c.lease_expires_at < now,
                            ),
                        )
                    )
                    .order_by(browser_jobs.c.updated_at.asc())
                    .limit(1)
                )
                if self.session_store.backend == "postgresql":
                    stmt = stmt.with_for_update(skip_locked=True)
                queued = conn.execute(stmt).mappings().one_or_none()
                if queued is None:
                    return None
                candidate = conn.execute(
                    select(candidates.c.row).where(
                        (candidates.c.session_id == queued["session_id"])
                        & (candidates.c.name_key == queued["name_key"])
                    )
                ).scalar_one_or_none()
                if not isinstance(candidate, dict) or str(candidate.get("browser_verification_state") or "") == "complete":
                    conn.execute(
                        update(browser_jobs)
                        .where(
                            (browser_jobs.c.session_id == queued["session_id"])
                            & (browser_jobs.c.name_key == queued["name_key"])
                        )
                        .values(state="completed", lease_expires_at=None, updated_at=now)
                    )
                    continue
                if not _browser_candidate(candidate):
                    conn.execute(
                        update(browser_jobs)
                        .where(
                            (browser_jobs.c.session_id == queued["session_id"])
                            & (browser_jobs.c.name_key == queued["name_key"])
                        )
                        .values(state="skipped", lease_expires_at=None, updated_at=now)
                    )
                    continue
                attempts = int(queued.get("attempts") or 0) + 1
                conn.execute(
                    update(browser_jobs)
                    .where(
                        (browser_jobs.c.session_id == queued["session_id"])
                        & (browser_jobs.c.name_key == queued["name_key"])
                    )
                    .values(
                        state="running",
                        attempts=attempts,
                        worker_id=str(worker_id or "")[:96] or None,
                        lease_expires_at=lease,
                        updated_at=now,
                    )
                )
                availability = candidate.get("availability") if isinstance(candidate.get("availability"), dict) else {}
                resources = [resource for resource in availability if resource in SOCIAL_RESOURCES or resource == "com"]
                return {
                    "id": str(queued.get("id") or "")[:36],
                    "session_id": queued["session_id"],
                    "name_key": queued["name_key"],
                    "run_id": str(candidate.get("run_id") or queued.get("run_id") or "")[:96],
                    "resources": resources,
                    "required_resources": list(availability.keys()),
                    "attempts": attempts,
                    "candidate": dict(candidate),
                }
        return None

    def complete(self, session_id, name_key):
        return self._set_state(session_id, name_key, "completed", None)

    def release(self, session_id, name_key, error=None, attempts=0):
        state = "failed" if int(attempts or 0) >= BROWSER_JOB_MAX_ATTEMPTS else "pending"
        return self._set_state(session_id, name_key, state, type(error).__name__ if error else None)

    def _set_state(self, session_id, name_key, state, error_type):
        engine = self._engine()
        now = _utcnow()
        with engine.begin() as conn:
            result = conn.execute(
                update(browser_jobs)
                .where(
                    (browser_jobs.c.session_id == session_id)
                    & (browser_jobs.c.name_key == name_key)
                )
                .values(
                    state=state,
                    worker_id=None,
                    lease_expires_at=None,
                    last_error_type=str(error_type or "")[:96] or None,
                    updated_at=now,
                )
            )
        return bool(result.rowcount)

    def counts(self):
        if not self.session_store.configured:
            return {}
        engine = self._engine()
        with engine.connect() as conn:
            rows = conn.execute(select(browser_jobs.c.state)).scalars().all()
        return {state: rows.count(state) for state in {"pending", "running", "completed", "skipped", "failed"}}


BROWSER_JOBS = BrowserJobQueue()


def install_candidate_enqueue(store=STORE, queue=BROWSER_JOBS):
    """Wrap the existing candidate mirror write without changing its API contract."""
    base = store.upsert_candidates
    if getattr(base, "_browser_queue_wrapper", False):
        return

    def wrapped(session_id, token, rows):
        safe_rows = queue.preserve_server_enrichment(session_id, rows)
        result = base(session_id, token, safe_rows)
        if result is not None:
            try:
                queue.enqueue_rows(session_id, safe_rows)
            except Exception:
                # Browser enrichment is optional post-fast work. Persistence must
                # never fail because its secondary queue is temporarily unhealthy.
                pass
        return result

    wrapped._browser_queue_wrapper = True
    store.upsert_candidates = wrapped


def run_queue_pump(stop_event, runtime, event_store, worker_id="browser-pump"):
    """Continuously claim foreground rows and submit them to bounded Browser Eye."""
    idle = BROWSER_QUEUE_IDLE_MS / 1000.0
    while not stop_event.is_set():
        try:
            claimed = BROWSER_JOBS.claim_next(worker_id)
        except Exception as error:
            print(f"NameMachine browser queue claim failed: {type(error).__name__}", flush=True)
            stop_event.wait(max(idle, 1.0))
            continue
        if not claimed:
            stop_event.wait(idle)
            continue

        session_id = claimed["session_id"]
        name_key = claimed["name_key"]
        attempts = claimed["attempts"]
        candidate = claimed.pop("candidate")

        def finished(success, error=None, *, sid=session_id, key=name_key, tries=attempts):
            try:
                if success:
                    BROWSER_JOBS.complete(sid, key)
                else:
                    BROWSER_JOBS.release(sid, key, error=error, attempts=tries)
            except Exception as callback_error:
                print(
                    f"NameMachine browser queue finalize failed: {type(callback_error).__name__}",
                    flush=True,
                )

        submitted = runtime.submit(claimed, candidate, event_store, on_done=finished)
        if not submitted:
            BROWSER_JOBS.release(session_id, name_key, attempts=max(0, attempts - 1))
            stop_event.wait(min(idle, 0.2))


__all__ = [
    "BROWSER_JOBS",
    "BrowserJobQueue",
    "browser_jobs",
    "install_candidate_enqueue",
    "run_queue_pump",
]
