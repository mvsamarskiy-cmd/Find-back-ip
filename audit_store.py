"""Ephemeral internal telemetry for NameMachine.

Client-facing reports are generated separately. This store keeps only operational
activity events needed for debugging and feedback/worker correlation. Events have
a short TTL (7 days by default) and are pruned by the background worker.
"""

from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import os

from sqlalchemy import Column, DateTime, ForeignKey, JSON, PrimaryKeyConstraint, String, Table, delete, insert, update
from sqlalchemy.exc import IntegrityError

from session_store import STORE, _parse_datetime, _utcnow, metadata, sessions


def _retention_days():
    try:
        value = int(os.environ.get("NAMEMACHINE_AUDIT_RETENTION_DAYS", "7"))
    except (TypeError, ValueError):
        value = 7
    return max(1, min(30, value))


AUDIT_RETENTION_DAYS = _retention_days()


audit_events = Table(
    "nm_audit_events",
    metadata,
    Column("session_id", String(36), ForeignKey("nm_sessions.id", ondelete="CASCADE"), nullable=False),
    Column("event_key", String(64), nullable=False),
    Column("event_at", DateTime(timezone=True), nullable=False),
    Column("event_type", String(48), nullable=False),
    Column("job_id", String(96), nullable=True),
    Column("payload", JSON, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("session_id", "event_key"),
)


def _event_key(row):
    canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditStore:
    def __init__(self, session_store=None):
        self.session_store = session_store or STORE
        self._table_ready = False
        self._last_error = None

    @property
    def configured(self):
        return self.session_store.configured

    def diagnostics(self):
        return {
            "configured": self.configured,
            "retention_days": AUDIT_RETENTION_DAYS,
            "purpose": "internal_ephemeral_telemetry",
            "client_report_includes_raw_audit": False,
            "last_error_type": type(self._last_error).__name__ if self._last_error else None,
        }

    def _ensure_table(self):
        engine = self.session_store._ensure_engine()
        if not self._table_ready:
            audit_events.create(engine, checkfirst=True)
            self._table_ready = True
        return engine

    def upsert_events(self, session_id, token, rows):
        engine = self._ensure_table()
        now = _utcnow()
        expires = now + timedelta(days=AUDIT_RETENTION_DAYS)
        accepted = 0
        with engine.begin() as conn:
            if not self.session_store._authorized(conn, session_id, token):
                return None
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                event_type = str(raw.get("type") or "")[:48]
                if not event_type:
                    continue
                event_at = _parse_datetime(raw.get("at"), fallback=now)
                job_id = str(raw.get("job_id") or "")[:96] or None
                payload = raw.get("details") if isinstance(raw.get("details"), dict) else {}
                normalized = {
                    "at": event_at.isoformat(),
                    "type": event_type,
                    "job_id": job_id,
                    "details": payload,
                }
                key = _event_key(normalized)
                values = {
                    "session_id": session_id,
                    "event_key": key,
                    "event_at": event_at,
                    "event_type": event_type,
                    "job_id": job_id,
                    "payload": payload,
                    "expires_at": expires,
                    "updated_at": now,
                }
                result = conn.execute(
                    update(audit_events)
                    .where((audit_events.c.session_id == session_id) & (audit_events.c.event_key == key))
                    .values(**values)
                )
                if not result.rowcount:
                    try:
                        conn.execute(insert(audit_events).values(**values))
                    except IntegrityError:
                        conn.execute(
                            update(audit_events)
                            .where((audit_events.c.session_id == session_id) & (audit_events.c.event_key == key))
                            .values(**values)
                        )
                accepted += 1
        self._last_error = None
        return {"accepted": accepted, "retention_days": AUDIT_RETENTION_DAYS}

    def prune_expired(self, now=None):
        if not self.configured:
            return 0
        engine = self._ensure_table()
        cutoff = now or _utcnow()
        with engine.begin() as conn:
            result = conn.execute(delete(audit_events).where(audit_events.c.expires_at <= cutoff))
        self._last_error = None
        return int(result.rowcount or 0)


AUDIT_STORE = AuditStore()


__all__ = ["AUDIT_RETENTION_DAYS", "AUDIT_STORE", "audit_events"]
