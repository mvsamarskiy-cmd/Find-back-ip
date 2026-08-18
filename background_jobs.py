"""Durable background search jobs for large NameMachine runs.

The queue deliberately lives in PostgreSQL/SQL storage instead of an in-memory
thread so a search can survive browser disconnects and web-process restarts. A
separate worker process claims jobs with a lease, checkpoints after every batch,
and writes candidates into the existing normalized session tables.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
import math
import os
import uuid

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    and_,
    func,
    insert,
    or_,
    select,
    update,
)

from session_store import (
    STORE,
    SessionStore,
    _iso,
    _utcnow,
    candidates,
    evidence,
    metadata,
    runs,
    sessions,
)


JOB_SCHEMA_VERSION = 1
MAX_BACKGROUND_TARGET = 20_000
DEFAULT_BATCH_SIZE = 20
MAX_BATCH_SIZE = 20
DEFAULT_LEASE_SECONDS = 180
BACKGROUND_VERIFY_WORKERS = max(1, min(8, int(os.environ.get("BACKGROUND_VERIFY_WORKERS", "4"))))

TERMINAL_STATES = {"completed", "cancelled", "failed"}
ACTIVE_STATES = {"pending", "running", "cancel_requested"}


search_jobs = Table(
    "nm_search_jobs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("session_id", String(36), ForeignKey("nm_sessions.id", ondelete="CASCADE"), nullable=False),
    Column("run_id", String(96), nullable=False),
    Column("state", String(24), nullable=False),
    Column("prompt", Text, nullable=False),
    Column("resources", JSON, nullable=False),
    Column("required_resources", JSON, nullable=False),
    Column("preferences", JSON, nullable=False),
    Column("search_context", JSON, nullable=False),
    Column("brand_dna", JSON, nullable=True),
    Column("generation_context", JSON, nullable=False),
    Column("target_count", Integer, nullable=False),
    Column("batch_size", Integer, nullable=False),
    Column("max_batches", Integer, nullable=False),
    Column("attempted_batches", Integer, nullable=False, default=0),
    Column("delivered_count", Integer, nullable=False, default=0),
    Column("worker_id", String(96), nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("stop_reason", String(64), nullable=True),
    Column("error_type", String(96), nullable=True),
    Column("error_message", String(300), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("revision", BigInteger, nullable=False, default=1),
)


search_job_seen = Table(
    "nm_search_job_seen",
    metadata,
    Column("job_id", String(36), ForeignKey("nm_search_jobs.id", ondelete="CASCADE"), nullable=False),
    Column("name_key", String(96), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("job_id", "name_key"),
)


def _clean_name(value):
    return "".join(ch for ch in str(value or "").strip() if ch.isascii() and ch.isalpha())[:96]


def _safe_int(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _job_dict(row):
    if row is None:
        return None
    item = dict(row)
    for key in ("created_at", "updated_at", "started_at", "finished_at", "lease_expires_at"):
        item[key] = _iso(item.get(key))
    return item


def _unknown_candidate(candidate, resources, error):
    row = dict(candidate or {})
    row["availability"] = {
        resource: {
            "status": "unknown",
            "detail": "Фонова перевірка не завершилася; доступність не підтверджена.",
            "url": "",
            "source": "background_worker",
            "method": "candidate_verification_error",
            "confidence": 0.0,
            "occupancy": "unknown",
            "claimability": "unconfirmed",
        }
        for resource in resources
    }
    row["verification"] = {}
    row["bundle_state"] = "unresolved"
    row["bundle_score"] = 0
    row["checked"] = False
    row["background_error_type"] = type(error).__name__
    return row


class SearchJobStore:
    """SQL-backed queue sharing the durable session engine and tables."""

    def __init__(self, session_store=None):
        self.session_store = session_store or STORE

    @property
    def configured(self):
        return self.session_store.configured

    def _engine(self):
        engine = self.session_store._ensure_engine()
        metadata.create_all(engine)
        return engine

    def diagnostics(self):
        return {
            "configured": self.configured,
            "schema_version": JOB_SCHEMA_VERSION,
            "max_target": MAX_BACKGROUND_TARGET,
            "max_batch_size": MAX_BATCH_SIZE,
            "lease_seconds": DEFAULT_LEASE_SECONDS,
            "worker_process_required": True,
            "durable": True,
        }

    def enqueue(self, session_id, token, payload):
        engine = self._engine()
        now = _utcnow()
        target = _safe_int(payload.get("target_count"), 500, 1, MAX_BACKGROUND_TARGET)
        batch_size = _safe_int(payload.get("batch_size"), DEFAULT_BATCH_SIZE, 1, MAX_BATCH_SIZE)
        minimum_batches = max(1, math.ceil(target / batch_size))
        max_batches = _safe_int(payload.get("max_batches"), minimum_batches * 3, minimum_batches, 3000)
        job_id = str(uuid.uuid4())
        run_id = str(payload.get("run_id") or f"bg-{job_id}")[:96]
        values = {
            "id": job_id,
            "session_id": session_id,
            "run_id": run_id,
            "state": "pending",
            "prompt": str(payload.get("prompt") or "")[:4000],
            "resources": list(payload.get("resources") or []),
            "required_resources": list(payload.get("required_resources") or []),
            "preferences": payload.get("preferences") if isinstance(payload.get("preferences"), dict) else {},
            "search_context": payload.get("search_context") if isinstance(payload.get("search_context"), dict) else {},
            "brand_dna": payload.get("brand_dna") if isinstance(payload.get("brand_dna"), dict) else None,
            "generation_context": payload.get("generation_context") if isinstance(payload.get("generation_context"), dict) else {},
            "target_count": target,
            "batch_size": batch_size,
            "max_batches": max_batches,
            "attempted_batches": 0,
            "delivered_count": 0,
            "worker_id": None,
            "lease_expires_at": None,
            "stop_reason": None,
            "error_type": None,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
            "revision": 1,
        }
        with engine.begin() as conn:
            if not SessionStore._authorized(conn, session_id, token):
                return None
            conn.execute(insert(search_jobs).values(**values))
            run_payload = {
                "id": run_id,
                "prompt": values["prompt"],
                "started": _iso(now),
                "finished": "",
                "status": "queued",
                "background_job_id": job_id,
                "startResultCount": int(
                    conn.execute(
                        select(func.count()).select_from(candidates).where(candidates.c.session_id == session_id)
                    ).scalar_one()
                ),
                "endResultCount": 0,
                "startBatch": 0,
                "endBatch": 0,
            }
            SessionStore._upsert(
                conn,
                runs,
                (runs.c.session_id == session_id) & (runs.c.run_id == run_id),
                {"session_id": session_id, "run_id": run_id, "payload": run_payload, "updated_at": now},
            )
            conn.execute(
                update(sessions)
                .where(sessions.c.id == session_id)
                .values(server_updated_at=now, revision=sessions.c.revision + 1)
            )
        return _job_dict(values)

    def get(self, session_id, token, job_id):
        engine = self._engine()
        with engine.connect() as conn:
            if not SessionStore._authorized(conn, session_id, token):
                return None
            row = conn.execute(
                select(search_jobs).where(
                    (search_jobs.c.id == job_id) & (search_jobs.c.session_id == session_id)
                )
            ).mappings().one_or_none()
        return _job_dict(row)

    def list(self, session_id, token, limit=20):
        engine = self._engine()
        limit = _safe_int(limit, 20, 1, 100)
        with engine.connect() as conn:
            if not SessionStore._authorized(conn, session_id, token):
                return None
            rows = conn.execute(
                select(search_jobs)
                .where(search_jobs.c.session_id == session_id)
                .order_by(search_jobs.c.created_at.desc())
                .limit(limit)
            ).mappings().all()
        return [_job_dict(row) for row in rows]

    def cancel(self, session_id, token, job_id):
        engine = self._engine()
        now = _utcnow()
        with engine.begin() as conn:
            if not SessionStore._authorized(conn, session_id, token):
                return None
            row = conn.execute(
                select(search_jobs).where(
                    (search_jobs.c.id == job_id) & (search_jobs.c.session_id == session_id)
                )
            ).mappings().one_or_none()
            if row is None:
                return None
            if row["state"] in TERMINAL_STATES:
                return _job_dict(row)
            next_state = "cancelled" if row["state"] == "pending" else "cancel_requested"
            values = {
                "state": next_state,
                "updated_at": now,
                "revision": search_jobs.c.revision + 1,
            }
            if next_state == "cancelled":
                values.update({"finished_at": now, "stop_reason": "user_cancelled", "lease_expires_at": None})
            conn.execute(update(search_jobs).where(search_jobs.c.id == job_id).values(**values))
            result = conn.execute(select(search_jobs).where(search_jobs.c.id == job_id)).mappings().one()
        return _job_dict(result)

    def claim_next(self, worker_id, lease_seconds=DEFAULT_LEASE_SECONDS):
        engine = self._engine()
        now = _utcnow()
        lease_until = now + timedelta(seconds=max(30, int(lease_seconds)))
        with engine.begin() as conn:
            condition = or_(
                search_jobs.c.state == "pending",
                and_(search_jobs.c.state == "running", search_jobs.c.lease_expires_at < now),
            )
            stmt = (
                select(search_jobs)
                .where(condition)
                .order_by(search_jobs.c.created_at.asc())
                .limit(1)
            )
            if self.session_store.backend == "postgresql":
                stmt = stmt.with_for_update(skip_locked=True)
            row = conn.execute(stmt).mappings().one_or_none()
            if row is None:
                return None
            values = {
                "state": "running",
                "worker_id": str(worker_id)[:96],
                "lease_expires_at": lease_until,
                "updated_at": now,
                "started_at": row["started_at"] or now,
                "revision": search_jobs.c.revision + 1,
                "error_type": None,
                "error_message": None,
            }
            conn.execute(update(search_jobs).where(search_jobs.c.id == row["id"]).values(**values))
            claimed = conn.execute(select(search_jobs).where(search_jobs.c.id == row["id"])).mappings().one()
            self._sync_run(conn, claimed, now)
        return _job_dict(claimed)

    def _sync_run(self, conn, job, now):
        total_results = int(
            conn.execute(
                select(func.count()).select_from(candidates).where(candidates.c.session_id == job["session_id"])
            ).scalar_one()
        )
        payload = {
            "id": job["run_id"],
            "prompt": job["prompt"],
            "started": _iso(job["started_at"] or job["created_at"]),
            "finished": _iso(job["finished_at"]) or "",
            "status": job["state"],
            "background_job_id": job["id"],
            "targetCount": int(job["target_count"]),
            "deliveredCount": int(job["delivered_count"]),
            "attemptedBatches": int(job["attempted_batches"]),
            "startResultCount": max(0, total_results - int(job["delivered_count"])),
            "endResultCount": total_results if job["state"] in TERMINAL_STATES else 0,
            "startBatch": 1,
            "endBatch": int(job["attempted_batches"]),
            "stopReason": job["stop_reason"] or "",
        }
        SessionStore._upsert(
            conn,
            runs,
            (runs.c.session_id == job["session_id"]) & (runs.c.run_id == job["run_id"]),
            {"session_id": job["session_id"], "run_id": job["run_id"], "payload": payload, "updated_at": now},
        )

    def is_cancel_requested(self, job_id):
        engine = self._engine()
        with engine.connect() as conn:
            state = conn.execute(select(search_jobs.c.state).where(search_jobs.c.id == job_id)).scalar_one_or_none()
        return state == "cancel_requested"

    def recent_names(self, session_id, limit=100):
        engine = self._engine()
        with engine.connect() as conn:
            rows = conn.execute(
                select(candidates.c.name)
                .where(candidates.c.session_id == session_id)
                .order_by(candidates.c.received_seq.desc(), candidates.c.updated_at.desc())
                .limit(max(1, min(500, int(limit))))
            ).scalars().all()
        return list(rows)

    def append_candidates(self, job_id, rows, batch_number):
        """Trusted-worker upsert; authorization happened when the job was enqueued."""
        engine = self._engine()
        now = _utcnow()
        inserted_count = 0
        with engine.begin() as conn:
            job = conn.execute(select(search_jobs).where(search_jobs.c.id == job_id)).mappings().one_or_none()
            if job is None or job["state"] not in {"running", "cancel_requested"}:
                return 0
            current_seq = int(
                conn.execute(
                    select(func.coalesce(func.max(candidates.c.received_seq), 0)).where(
                        candidates.c.session_id == job["session_id"]
                    )
                ).scalar_one()
            )
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                name = _clean_name(raw.get("name"))
                key = name.lower()
                if not key:
                    continue
                existing = conn.execute(
                    select(candidates.c.name_key).where(
                        (candidates.c.session_id == job["session_id"]) & (candidates.c.name_key == key)
                    )
                ).scalar_one_or_none()
                if existing:
                    SessionStore._upsert(
                        conn,
                        search_job_seen,
                        (search_job_seen.c.job_id == job_id) & (search_job_seen.c.name_key == key),
                        {"job_id": job_id, "name_key": key, "created_at": now},
                    )
                    continue
                current_seq += 1
                row = dict(raw)
                row.update({
                    "name": name,
                    "run_id": job["run_id"],
                    "batch_number": int(batch_number),
                    "received_seq": current_seq,
                    "received_at": _iso(now),
                })
                conn.execute(
                    insert(candidates).values(
                        session_id=job["session_id"],
                        name_key=key,
                        name=name,
                        row=row,
                        received_seq=current_seq,
                        received_at=now,
                        run_id=job["run_id"],
                        batch_number=int(batch_number),
                        updated_at=now,
                    )
                )
                SessionStore._upsert(
                    conn,
                    search_job_seen,
                    (search_job_seen.c.job_id == job_id) & (search_job_seen.c.name_key == key),
                    {"job_id": job_id, "name_key": key, "created_at": now},
                )
                availability = row.get("availability") if isinstance(row.get("availability"), dict) else {}
                verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
                for resource, payload in availability.items():
                    if not isinstance(payload, dict):
                        continue
                    resource_key = str(resource)[:32]
                    SessionStore._upsert(
                        conn,
                        evidence,
                        (evidence.c.session_id == job["session_id"])
                        & (evidence.c.name_key == key)
                        & (evidence.c.resource == resource_key),
                        {
                            "session_id": job["session_id"],
                            "name_key": key,
                            "resource": resource_key,
                            "availability": payload,
                            "verification": verification.get(resource) if isinstance(verification.get(resource), dict) else None,
                            "updated_at": now,
                        },
                    )
                inserted_count += 1
            if inserted_count:
                conn.execute(
                    update(sessions)
                    .where(sessions.c.id == job["session_id"])
                    .values(server_updated_at=now, revision=sessions.c.revision + 1)
                )
        return inserted_count

    def checkpoint(self, job_id, worker_id, attempted_batches, delivered_count, lease_seconds=DEFAULT_LEASE_SECONDS):
        engine = self._engine()
        now = _utcnow()
        lease_until = now + timedelta(seconds=max(30, int(lease_seconds)))
        with engine.begin() as conn:
            conn.execute(
                update(search_jobs)
                .where((search_jobs.c.id == job_id) & (search_jobs.c.worker_id == str(worker_id)[:96]))
                .values(
                    attempted_batches=max(0, int(attempted_batches)),
                    delivered_count=max(0, int(delivered_count)),
                    lease_expires_at=lease_until,
                    updated_at=now,
                    revision=search_jobs.c.revision + 1,
                )
            )
            row = conn.execute(select(search_jobs).where(search_jobs.c.id == job_id)).mappings().one_or_none()
            if row:
                self._sync_run(conn, row, now)
        return _job_dict(row)

    def finish(self, job_id, worker_id, state, stop_reason, attempted_batches, delivered_count):
        if state not in {"completed", "cancelled"}:
            raise ValueError("Invalid terminal state")
        engine = self._engine()
        now = _utcnow()
        with engine.begin() as conn:
            conn.execute(
                update(search_jobs)
                .where((search_jobs.c.id == job_id) & (search_jobs.c.worker_id == str(worker_id)[:96]))
                .values(
                    state=state,
                    stop_reason=str(stop_reason)[:64],
                    attempted_batches=max(0, int(attempted_batches)),
                    delivered_count=max(0, int(delivered_count)),
                    lease_expires_at=None,
                    finished_at=now,
                    updated_at=now,
                    revision=search_jobs.c.revision + 1,
                )
            )
            row = conn.execute(select(search_jobs).where(search_jobs.c.id == job_id)).mappings().one_or_none()
            if row:
                self._sync_run(conn, row, now)
        return _job_dict(row)

    def fail(self, job_id, worker_id, error, attempted_batches, delivered_count):
        engine = self._engine()
        now = _utcnow()
        with engine.begin() as conn:
            conn.execute(
                update(search_jobs)
                .where((search_jobs.c.id == job_id) & (search_jobs.c.worker_id == str(worker_id)[:96]))
                .values(
                    state="failed",
                    stop_reason="worker_error",
                    error_type=type(error).__name__[:96],
                    error_message=str(error)[:300],
                    attempted_batches=max(0, int(attempted_batches)),
                    delivered_count=max(0, int(delivered_count)),
                    lease_expires_at=None,
                    finished_at=now,
                    updated_at=now,
                    revision=search_jobs.c.revision + 1,
                )
            )
            row = conn.execute(select(search_jobs).where(search_jobs.c.id == job_id)).mappings().one_or_none()
            if row:
                self._sync_run(conn, row, now)
        return _job_dict(row)

    def release_to_pending(self, job_id, worker_id, attempted_batches, delivered_count):
        engine = self._engine()
        now = _utcnow()
        with engine.begin() as conn:
            conn.execute(
                update(search_jobs)
                .where((search_jobs.c.id == job_id) & (search_jobs.c.worker_id == str(worker_id)[:96]))
                .values(
                    state="pending",
                    worker_id=None,
                    lease_expires_at=None,
                    stop_reason="worker_shutdown",
                    attempted_batches=max(0, int(attempted_batches)),
                    delivered_count=max(0, int(delivered_count)),
                    updated_at=now,
                    revision=search_jobs.c.revision + 1,
                )
            )
            row = conn.execute(select(search_jobs).where(search_jobs.c.id == job_id)).mappings().one_or_none()
            if row:
                self._sync_run(conn, row, now)
        return _job_dict(row)


def run_one_job(
    store,
    worker_id,
    generate_batch,
    verify_candidate,
    *,
    verify_workers=BACKGROUND_VERIFY_WORKERS,
    should_stop=None,
):
    """Claim and execute one durable job, checkpointing after each batch.

    `generate_batch(job, count, generation_context)` and
    `verify_candidate(job, candidate)` are injected so the queue can be tested
    deterministically while the real worker uses the existing AI/verifier stack.
    """
    job = store.claim_next(worker_id)
    if not job:
        return None

    attempted = int(job.get("attempted_batches") or 0)
    delivered = int(job.get("delivered_count") or 0)
    target = int(job["target_count"])
    max_batches = int(job["max_batches"])
    batch_size = int(job["batch_size"])
    resources = list(job.get("resources") or [])

    try:
        while delivered < target and attempted < max_batches:
            if should_stop and should_stop():
                return store.release_to_pending(job["id"], worker_id, attempted, delivered)
            if store.is_cancel_requested(job["id"]):
                return store.finish(job["id"], worker_id, "cancelled", "user_cancelled", attempted, delivered)

            attempted += 1
            count = min(batch_size, target - delivered)
            context = dict(job.get("generation_context") or {})
            context["batch_number"] = min(5, attempted)
            context["exclude_names"] = store.recent_names(job["session_id"], 100)
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
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="background-verify") as executor:
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
            delivered += inserted
            job = store.checkpoint(job["id"], worker_id, attempted, delivered) or job

        reason = "target_reached" if delivered >= target else "max_batches"
        return store.finish(job["id"], worker_id, "completed", reason, attempted, delivered)
    except Exception as error:
        return store.fail(job["id"], worker_id, error, attempted, delivered)


JOB_STORE = SearchJobStore()


__all__ = [
    "BACKGROUND_VERIFY_WORKERS",
    "DEFAULT_BATCH_SIZE",
    "JOB_SCHEMA_VERSION",
    "JOB_STORE",
    "MAX_BACKGROUND_TARGET",
    "MAX_BATCH_SIZE",
    "SearchJobStore",
    "run_one_job",
    "search_jobs",
]
