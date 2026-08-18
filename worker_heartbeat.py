"""Database heartbeat for NameMachine background search workers."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import Column, DateTime, String, Table, delete, insert, select, update

from session_store import STORE, _iso, _utcnow, metadata


ONLINE_SECONDS = 90

worker_heartbeats = Table(
    "nm_worker_heartbeats",
    metadata,
    Column("worker_id", String(96), primary_key=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
)


def beat(session_store=None, worker_id="worker"):
    store = session_store or STORE
    engine = store._ensure_engine()
    metadata.create_all(engine)
    now = _utcnow()
    key = str(worker_id or "worker")[:96]
    with engine.begin() as conn:
        changed = conn.execute(
            update(worker_heartbeats)
            .where(worker_heartbeats.c.worker_id == key)
            .values(last_seen_at=now)
        )
        if not changed.rowcount:
            conn.execute(
                insert(worker_heartbeats).values(
                    worker_id=key,
                    started_at=now,
                    last_seen_at=now,
                )
            )
    return now


def remove(session_store=None, worker_id="worker"):
    store = session_store or STORE
    if not store.configured:
        return
    engine = store._ensure_engine()
    with engine.begin() as conn:
        conn.execute(delete(worker_heartbeats).where(worker_heartbeats.c.worker_id == str(worker_id)[:96]))


def status(session_store=None, online_seconds=ONLINE_SECONDS):
    store = session_store or STORE
    if not store.configured:
        return {"worker_online": False, "worker_count": 0, "last_seen_at": None}
    try:
        engine = store._ensure_engine()
        metadata.create_all(engine)
        now = _utcnow()
        cutoff = now - timedelta(seconds=max(30, int(online_seconds)))
        with engine.connect() as conn:
            rows = conn.execute(
                select(worker_heartbeats.c.worker_id, worker_heartbeats.c.last_seen_at)
                .where(worker_heartbeats.c.last_seen_at >= cutoff)
                .order_by(worker_heartbeats.c.last_seen_at.desc())
            ).mappings().all()
        return {
            "worker_online": bool(rows),
            "worker_count": len(rows),
            "last_seen_at": _iso(rows[0]["last_seen_at"]) if rows else None,
        }
    except Exception:
        return {"worker_online": False, "worker_count": 0, "last_seen_at": None}


__all__ = ["ONLINE_SECONDS", "beat", "remove", "status", "worker_heartbeats"]
