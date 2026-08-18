"""Durable candidate lifecycle events for background NameMachine searches.

Final candidate rows remain in the normal session candidate table. This module
adds a short-lived event stream so a browser can see a real generated candidate
immediately, then receive its final verifier result without abusing received_seq
or rewriting historical ordering.
"""
from __future__ import annotations

from datetime import timedelta
import os

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    JSON,
    PrimaryKeyConstraint,
    String,
    Table,
    delete,
    func,
    insert,
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
    sessions,
)


MAX_EVENT_PAGE = 200
DEFAULT_EVENT_RETENTION_DAYS = 7


def _bounded_int_env(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


EVENT_RETENTION_DAYS = _bounded_int_env(
    "NAMEMACHINE_CANDIDATE_EVENT_RETENTION_DAYS",
    DEFAULT_EVENT_RETENTION_DAYS,
    1,
    30,
)


candidate_events = Table(
    "nm_candidate_events",
    metadata,
    Column("session_id", String(36), ForeignKey("nm_sessions.id", ondelete="CASCADE"), nullable=False),
    Column("event_seq", BigInteger, nullable=False),
    Column("job_id", String(36), nullable=False),
    Column("run_id", String(96), nullable=False),
    Column("name_key", String(96), nullable=False),
    Column("event_type", String(40), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("session_id", "event_seq"),
)


def _clean_name(value):
    return "".join(ch for ch in str(value or "").strip() if ch.isascii() and ch.isalpha())[:96]


def _pending_resource(resource):
    return {
        "status": "checking",
        "detail": "Фонова перевірка виконується.",
        "url": "",
        "source": "background_worker",
        "method": "pending",
        "confidence": 0.0,
        "occupancy": "unknown",
        "claimability": "unconfirmed",
        "resource": resource,
    }


class DurableCandidateEventStore:
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
            "durable_live_events": True,
            "event_types": ["candidate_generated", "candidate_completed"],
            "retention_days": EVENT_RETENTION_DAYS,
            "final_candidate_rows_durable": True,
            "events_are_transient": True,
        }

    def _next_event_seq(self, conn, session_id):
        # Serialize event sequence allocation per session on PostgreSQL. SQLite
        # writes are already serialized and the worker emits DB mutations from
        # one coordinator thread, so the same max+1 contract remains deterministic.
        if self.session_store.backend == "postgresql":
            conn.execute(
                select(sessions.c.id)
                .where(sessions.c.id == session_id)
                .with_for_update()
            ).scalar_one()
        current = conn.execute(
            select(func.coalesce(func.max(candidate_events.c.event_seq), 0)).where(
                candidate_events.c.session_id == session_id
            )
        ).scalar_one()
        return int(current or 0) + 1

    def _emit(self, conn, job, name_key, event_type, payload, now):
        seq = self._next_event_seq(conn, job["session_id"])
        conn.execute(
            insert(candidate_events).values(
                session_id=job["session_id"],
                event_seq=seq,
                job_id=str(job.get("id") or "")[:36],
                run_id=str(job.get("run_id") or "")[:96],
                name_key=name_key[:96],
                event_type=str(event_type)[:40],
                payload=payload if isinstance(payload, dict) else {},
                created_at=now,
                expires_at=now + timedelta(days=EVENT_RETENTION_DAYS),
            )
        )
        return seq

    def stage_candidates(self, job, rows, batch_number):
        """Persist generated candidates immediately in `checking` state.

        Only previously unseen session names are staged. This preserves the old
        dedupe contract and lets the worker keep generating until its actual result
        goal or search budget is reached.
        """
        engine = self._engine()
        now = _utcnow()
        staged = []
        resources = [str(item) for item in (job.get("resources") or []) if str(item)]
        with engine.begin() as conn:
            current_seq = int(
                conn.execute(
                    select(func.coalesce(func.max(candidates.c.received_seq), 0)).where(
                        candidates.c.session_id == job["session_id"]
                    )
                ).scalar_one()
            )
            for raw in rows or []:
                if not isinstance(raw, dict):
                    continue
                name = _clean_name(raw.get("name"))
                key = name.lower()
                if not key:
                    continue
                existing = conn.execute(
                    select(candidates.c.name_key).where(
                        (candidates.c.session_id == job["session_id"])
                        & (candidates.c.name_key == key)
                    )
                ).scalar_one_or_none()
                if existing:
                    continue

                current_seq += 1
                row = dict(raw)
                row.update({
                    "name": name,
                    "availability": {resource: _pending_resource(resource) for resource in resources},
                    "verification": {},
                    "checked": False,
                    "verification_state": "checking",
                    "resource_progress": {"completed": 0, "total": len(resources)},
                    "run_id": str(job.get("run_id") or "")[:96],
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
                        run_id=row["run_id"],
                        batch_number=int(batch_number),
                        updated_at=now,
                    )
                )
                event_seq = self._emit(
                    conn,
                    job,
                    key,
                    "candidate_generated",
                    {"row": row, "resources": resources},
                    now,
                )
                row["lifecycle_event_seq"] = event_seq
                staged.append(row)

            if staged:
                conn.execute(
                    update(sessions)
                    .where(sessions.c.id == job["session_id"])
                    .values(server_updated_at=now, revision=sessions.c.revision + 1)
                )
        return staged

    def finalize_candidate(self, job, final_row, batch_number):
        """Replace one staged row with its final verifier result and emit an event."""
        if not isinstance(final_row, dict):
            return None
        name = _clean_name(final_row.get("name"))
        key = name.lower()
        if not key:
            return None
        engine = self._engine()
        now = _utcnow()
        with engine.begin() as conn:
            existing = conn.execute(
                select(candidates).where(
                    (candidates.c.session_id == job["session_id"])
                    & (candidates.c.name_key == key)
                )
            ).mappings().one_or_none()
            if existing is None:
                return None

            prior = dict(existing.get("row") or {})
            row = dict(prior)
            row.update(final_row)
            row.update({
                "name": name,
                "checked": True,
                "verification_state": "complete",
                "run_id": prior.get("run_id") or str(job.get("run_id") or "")[:96],
                "batch_number": int(prior.get("batch_number") or batch_number),
                "received_seq": int(existing.get("received_seq") or prior.get("received_seq") or 0),
                "received_at": prior.get("received_at") or _iso(existing.get("received_at")) or _iso(now),
            })
            row.pop("resource_progress", None)
            row.pop("lifecycle_event_seq", None)

            conn.execute(
                update(candidates)
                .where(
                    (candidates.c.session_id == job["session_id"])
                    & (candidates.c.name_key == key)
                )
                .values(
                    name=name,
                    row=row,
                    run_id=row["run_id"],
                    batch_number=row["batch_number"],
                    updated_at=now,
                )
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

            event_seq = self._emit(
                conn,
                job,
                key,
                "candidate_completed",
                {"row": row},
                now,
            )
            conn.execute(
                update(sessions)
                .where(sessions.c.id == job["session_id"])
                .values(server_updated_at=now, revision=sessions.c.revision + 1)
            )
        result = dict(row)
        result["lifecycle_event_seq"] = event_seq
        return result

    def pending_for_job(self, job, limit=100):
        """Recover a small set of staged-but-unfinished rows after worker restart."""
        engine = self._engine()
        with engine.connect() as conn:
            rows = conn.execute(
                select(candidates.c.row)
                .where(
                    (candidates.c.session_id == job["session_id"])
                    & (candidates.c.run_id == job.get("run_id"))
                )
                .order_by(candidates.c.updated_at.desc())
                .limit(max(1, min(200, int(limit))))
            ).scalars().all()
        pending = []
        for raw in rows:
            row = dict(raw or {})
            if row.get("checked") is False and str(row.get("verification_state") or "") == "checking":
                pending.append(row)
        return pending

    def since(self, session_id, token, after_seq=0, limit=100):
        engine = self._engine()
        try:
            cursor = max(0, int(after_seq or 0))
        except (TypeError, ValueError):
            cursor = 0
        try:
            page_size = max(1, min(MAX_EVENT_PAGE, int(limit or 100)))
        except (TypeError, ValueError):
            page_size = 100
        now = _utcnow()

        with engine.begin() as conn:
            if not SessionStore._authorized(conn, session_id, token):
                return None
            conn.execute(
                delete(candidate_events).where(candidate_events.c.expires_at <= now)
            )
            rows = conn.execute(
                select(candidate_events)
                .where(
                    (candidate_events.c.session_id == session_id)
                    & (candidate_events.c.event_seq > cursor)
                )
                .order_by(candidate_events.c.event_seq.asc())
                .limit(page_size + 1)
            ).mappings().all()

        has_more = len(rows) > page_size
        page = rows[:page_size]
        events = []
        next_cursor = cursor
        for raw in page:
            item = dict(raw)
            item["created_at"] = _iso(item.get("created_at"))
            item["expires_at"] = _iso(item.get("expires_at"))
            item["payload"] = dict(item.get("payload") or {})
            item["event_seq"] = int(item.get("event_seq") or 0)
            next_cursor = max(next_cursor, item["event_seq"])
            events.append(item)
        return {
            "events": events,
            "after_seq": cursor,
            "next_after_seq": next_cursor,
            "has_more": has_more,
            "limit": page_size,
            "retention_days": EVENT_RETENTION_DAYS,
        }


LIVE_CANDIDATES = DurableCandidateEventStore()


__all__ = [
    "DEFAULT_EVENT_RETENTION_DAYS",
    "EVENT_RETENTION_DAYS",
    "LIVE_CANDIDATES",
    "MAX_EVENT_PAGE",
    "DurableCandidateEventStore",
    "candidate_events",
]
