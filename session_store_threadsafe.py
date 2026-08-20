"""Process-local serialization for lazy SessionStore engine/schema startup.

NameMachine intentionally starts several independent worker threads (search,
telemetry retention, and Browser Intelligence pumps). SQLAlchemy `create_all()` is
safe to call repeatedly, but multiple first calls racing against the same fresh
PostgreSQL schema can still collide while creating catalog objects. The original
SessionStore lazy initializer was not protected by a lock.

Install this wrapper before serving requests or starting worker threads. The fast
path remains lock-free after initialization; only first-time engine/schema setup
is serialized. This changes no persistence or authorization semantics.
"""
from __future__ import annotations

from threading import RLock

from session_store import SessionStore


_INIT_LOCK = RLock()


def install_threadsafe_session_store():
    current = SessionStore._ensure_engine
    if getattr(current, "_namemachine_threadsafe_init", False):
        return

    def ensure_engine_threadsafe(self):
        if self._engine is not None and self._initialized:
            return self._engine
        with _INIT_LOCK:
            return current(self)

    ensure_engine_threadsafe._namemachine_threadsafe_init = True
    ensure_engine_threadsafe._namemachine_original = current
    SessionStore._ensure_engine = ensure_engine_threadsafe


__all__ = ["install_threadsafe_session_store"]
