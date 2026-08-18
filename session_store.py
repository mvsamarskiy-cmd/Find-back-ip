"""Durable NameMachine session persistence.

The browser remains the immediate/offline working copy. When a database is
configured, this module stores the same project as normalized session, run,
feedback, candidate, and per-resource evidence rows so large searches do not
depend on one browser's localStorage.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import os
import secrets
import uuid

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError


SCHEMA_VERSION = 1

metadata = MetaData()

sessions = Table(
    "nm_sessions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("token_hash", String(64), nullable=False),
    Column("client_session_id", String(96), nullable=True),
    Column("title", String(160), nullable=False, default="Нова сесія"),
    Column("prompt_history", JSON, nullable=False),
    Column("resources", JSON, nullable=False),
    Column("shortlist", JSON, nullable=False),
    Column("direction_anchors", JSON, nullable=False),
    Column("batch_counter", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("client_updated_at", DateTime(timezone=True), nullable=False),
    Column("server_updated_at", DateTime(timezone=True), nullable=False),
    Column("revision", BigInteger, nullable=False, default=1),
)

runs = Table(
    "nm_session_runs",
    metadata,
    Column("session_id", String(36), ForeignKey("nm_sessions.id", ondelete="CASCADE"), nullable=False),
    Column("run_id", String(96), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("session_id", "run_id"),
)

feedback = Table(
    "nm_session_feedback",
    metadata,
    Column("session_id", String(36), ForeignKey("nm_sessions.id", ondelete="CASCADE"), nullable=False),
    Column("name_key", String(96), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("session_id", "name_key"),
)

candidates = Table(
    "nm_session_candidates",
    metadata,
    Column("session_id", String(36), ForeignKey("nm_sessions.id", ondelete="CASCADE"), nullable=False),
    Column("name_key", String(96), nullable=False),
    Column("name", String(96), nullable=False),
    Column("row", JSON, nullable=False),
    Column("received_seq", BigInteger, nullable=False, default=0),
    Column("received_at", DateTime(timezone=True), nullable=True),
    Column("run_id", String(96), nullable=True),
    Column("batch_number", Integer, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("session_id", "name_key"),
)

evidence = Table(
    "nm_candidate_evidence",
    metadata,
    Column("session_id", String(36), ForeignKey("nm_sessions.id", ondelete="CASCADE"), nullable=False),
    Column("name_key", String(96), nullable=False),
    Column("resource", String(32), nullable=False),
    Column("availability", JSON, nullable=False),
    Column("verification", JSON, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("session_id", "name_key", "resource"),
)


def _utcnow():
    return datetime.now(timezone.utc)


def _parse_datetime(value, fallback=None):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return fallback or _utcnow()
    else:
        return fallback or _utcnow()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value):
    if not value:
        return None
    return _parse_datetime(value).isoformat().replace("+00:00", "Z")


def _hash_token(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _database_url_from_env():
    return os.environ.get("NAMEMACHINE_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""


def _normalize_database_url(url):
    value = str(url or "").strip()
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


def _backend_name(url):
    value = str(url or "")
    if value.startswith(("postgres://", "postgresql://", "postgresql+")):
        return "postgresql"
    if value.startswith("sqlite"):
        return "sqlite"
    return "none"


class SessionStore:
    """Small SQLAlchemy Core store with capability-token authorization."""

    def __init__(self, database_url=None):
        self.database_url = database_url if database_url is not None else _database_url_from_env()
        self.normalized_url = _normalize_database_url(self.database_url)
        self.backend = _backend_name(self.database_url)
        self._engine = None
        self._initialized = False
        self._last_error = None

    @property
    def configured(self):
        return bool(self.normalized_url)

    def diagnostics(self):
        return {
            "configured": self.configured,
            "backend": self.backend,
            "schema_version": SCHEMA_VERSION,
            "normalized_entities": ["session", "run", "candidate", "evidence", "feedback"],
            "last_error_type": type(self._last_error).__name__ if self._last_error else None,
        }

    def _ensure_engine(self):
        if not self.configured:
            raise RuntimeError("Session database is not configured")
        if self._engine is None:
            self._engine = create_engine(self.normalized_url, pool_pre_ping=True, future=True)
        if not self._initialized:
            metadata.create_all(self._engine)
            self._initialized = True
        return self._engine

    def ensure_ready(self):
        try:
            self._ensure_engine()
            self._last_error = None
            return True
        except Exception as error:
            self._last_error = error
            return False

    @staticmethod
    def _upsert(conn, table, where_clause, values):
        result = conn.execute(update(table).where(where_clause).values(**values))
        if result.rowcount:
            return
        try:
            conn.execute(insert(table).values(**values))
        except IntegrityError:
            conn.execute(update(table).where(where_clause).values(**values))

    @staticmethod
    def _authorized(conn, session_id, token):
        stored = conn.execute(
            select(sessions.c.token_hash).where(sessions.c.id == session_id)
        ).scalar_one_or_none()
        if not stored or not token:
            return False
        return hmac.compare_digest(stored, _hash_token(token))

    @staticmethod
    def _session_values(payload, now=None):
        now = now or _utcnow()
        return {
            "client_session_id": payload.get("client_session_id"),
            "title": payload.get("title") or "Нова сесія",
            "prompt_history": payload.get("prompt_history") or [],
            "resources": payload.get("resources") or [],
            "shortlist": payload.get("shortlist") or [],
            "direction_anchors": payload.get("direction_anchors") or [],
            "batch_counter": int(payload.get("batch_counter") or 0),
            "client_updated_at": _parse_datetime(payload.get("updated"), fallback=now),
            "server_updated_at": now,
        }

    def create_session(self, payload):
        engine = self._ensure_engine()
        session_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        now = _utcnow()
        values = self._session_values(payload, now=now)
        values.update({
            "id": session_id,
            "token_hash": _hash_token(token),
            "created_at": _parse_datetime(payload.get("created"), fallback=now),
            "revision": 1,
        })
        with engine.begin() as conn:
            conn.execute(insert(sessions).values(**values))
            self._upsert_runs(conn, session_id, payload.get("runs") or [], now)
            self._upsert_feedback(conn, session_id, payload.get("feedback") or {}, now)
        return {
            "id": session_id,
            "token": token,
            "revision": 1,
            "server_updated_at": _iso(now),
        }

    def update_session(self, session_id, token, payload):
        engine = self._ensure_engine()
        now = _utcnow()
        with engine.begin() as conn:
            if not self._authorized(conn, session_id, token):
                return None
            values = self._session_values(payload, now=now)
            conn.execute(
                update(sessions)
                .where(sessions.c.id == session_id)
                .values(**values, revision=sessions.c.revision + 1)
            )
            self._upsert_runs(conn, session_id, payload.get("runs") or [], now)
            self._upsert_feedback(conn, session_id, payload.get("feedback") or {}, now)
            row = conn.execute(
                select(sessions.c.revision, sessions.c.server_updated_at).where(sessions.c.id == session_id)
            ).mappings().one()
        return {"revision": int(row["revision"]), "server_updated_at": _iso(row["server_updated_at"])}

    def _upsert_runs(self, conn, session_id, rows, now):
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            run_id = str(raw.get("id") or "")[:96]
            if not run_id:
                continue
            values = {
                "session_id": session_id,
                "run_id": run_id,
                "payload": raw,
                "updated_at": now,
            }
            self._upsert(
                conn,
                runs,
                (runs.c.session_id == session_id) & (runs.c.run_id == run_id),
                values,
            )

    def _upsert_feedback(self, conn, session_id, items, now):
        if not isinstance(items, dict):
            return
        for name_key, raw in items.items():
            key = str(name_key or "").strip().lower()[:96]
            if not key or not isinstance(raw, dict):
                continue
            values = {
                "session_id": session_id,
                "name_key": key,
                "payload": raw,
                "updated_at": now,
            }
            self._upsert(
                conn,
                feedback,
                (feedback.c.session_id == session_id) & (feedback.c.name_key == key),
                values,
            )

    def upsert_candidates(self, session_id, token, rows):
        engine = self._ensure_engine()
        now = _utcnow()
        accepted = 0
        with engine.begin() as conn:
            if not self._authorized(conn, session_id, token):
                return None
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("name") or "").strip()[:96]
                key = name.lower()
                if not key:
                    continue
                values = {
                    "session_id": session_id,
                    "name_key": key,
                    "name": name,
                    "row": raw,
                    "received_seq": int(raw.get("received_seq") or 0),
                    "received_at": _parse_datetime(raw.get("received_at"), fallback=None) if raw.get("received_at") else None,
                    "run_id": str(raw.get("run_id") or "")[:96] or None,
                    "batch_number": int(raw.get("batch_number") or 0) or None,
                    "updated_at": now,
                }
                self._upsert(
                    conn,
                    candidates,
                    (candidates.c.session_id == session_id) & (candidates.c.name_key == key),
                    values,
                )
                self._replace_evidence(conn, session_id, key, raw, now)
                accepted += 1
            if accepted:
                conn.execute(
                    update(sessions)
                    .where(sessions.c.id == session_id)
                    .values(server_updated_at=now, revision=sessions.c.revision + 1)
                )
            row = conn.execute(
                select(sessions.c.revision, sessions.c.server_updated_at).where(sessions.c.id == session_id)
            ).mappings().one()
        return {
            "accepted": accepted,
            "revision": int(row["revision"]),
            "server_updated_at": _iso(row["server_updated_at"]),
        }

    def _replace_evidence(self, conn, session_id, name_key, row, now):
        availability = row.get("availability") if isinstance(row.get("availability"), dict) else {}
        verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
        for resource, payload in availability.items():
            if not isinstance(payload, dict):
                continue
            resource_key = str(resource)[:32]
            values = {
                "session_id": session_id,
                "name_key": name_key,
                "resource": resource_key,
                "availability": payload,
                "verification": verification.get(resource) if isinstance(verification.get(resource), dict) else None,
                "updated_at": now,
            }
            self._upsert(
                conn,
                evidence,
                (evidence.c.session_id == session_id)
                & (evidence.c.name_key == name_key)
                & (evidence.c.resource == resource_key),
                values,
            )

    def load_session(self, session_id, token):
        engine = self._ensure_engine()
        with engine.connect() as conn:
            if not self._authorized(conn, session_id, token):
                return None
            base = conn.execute(select(sessions).where(sessions.c.id == session_id)).mappings().one()
            run_rows = conn.execute(
                select(runs.c.payload).where(runs.c.session_id == session_id).order_by(runs.c.updated_at.asc())
            ).scalars().all()
            feedback_rows = conn.execute(
                select(feedback.c.name_key, feedback.c.payload).where(feedback.c.session_id == session_id)
            ).mappings().all()
            candidate_rows = conn.execute(
                select(candidates.c.row)
                .where(candidates.c.session_id == session_id)
                .order_by(candidates.c.received_seq.asc(), candidates.c.updated_at.asc())
            ).scalars().all()
        return {
            "client_session_id": base["client_session_id"],
            "title": base["title"],
            "promptHistory": base["prompt_history"] or [],
            "resources": base["resources"] or [],
            "results": candidate_rows,
            "feedback": {row["name_key"]: row["payload"] for row in feedback_rows},
            "shortlist": base["shortlist"] or [],
            "directionAnchors": base["direction_anchors"] or [],
            "runs": run_rows,
            "batchCounter": int(base["batch_counter"] or 0),
            "created": _iso(base["created_at"]),
            "updated": _iso(base["client_updated_at"]),
            "server_updated_at": _iso(base["server_updated_at"]),
            "revision": int(base["revision"] or 0),
        }

    def delete_session(self, session_id, token):
        engine = self._ensure_engine()
        with engine.begin() as conn:
            if not self._authorized(conn, session_id, token):
                return False
            conn.execute(delete(sessions).where(sessions.c.id == session_id))
        return True


STORE = SessionStore()


__all__ = ["SCHEMA_VERSION", "STORE", "SessionStore"]
