"""Production worker entrypoint with short-lived audit cleanup."""

from __future__ import annotations

import threading

from audit_store import AUDIT_STORE
from entry_mode_backend import install_entry_mode_intelligence
import search_worker


# The web bootstrap installs the same wrapper for foreground/HTTP generation.
# Background generation imports app directly, so install it here as well before
# the worker loop can interpret its first durable job.
install_entry_mode_intelligence(search_worker.app_module)


def _audit_cleanup_loop():
    # Run immediately, then at most hourly. Expired telemetry therefore disappears
    # within roughly one hour after its TTL even when no new browser session writes.
    while not search_worker.STOP.is_set():
        try:
            removed = AUDIT_STORE.prune_expired()
            if removed:
                print(f"NameMachine audit retention: removed {removed} expired events", flush=True)
        except Exception as error:
            print(f"NameMachine audit retention failed: {type(error).__name__}", flush=True)
        search_worker.STOP.wait(3600.0)


def main():
    sweeper = threading.Thread(
        target=_audit_cleanup_loop,
        name="namemachine-audit-retention",
        daemon=True,
    )
    sweeper.start()
    try:
        return search_worker.main()
    finally:
        search_worker.STOP.set()
        sweeper.join(timeout=2.0)


if __name__ == "__main__":
    raise SystemExit(main())
