"""Production worker entrypoint with short-lived telemetry cleanup."""

from __future__ import annotations

import threading

from audit_store import AUDIT_STORE
from browser_enrichment import BROWSER_ENRICHMENT, install_live_background_enrichment
from durable_candidate_events import LIVE_CANDIDATES
from entry_mode_backend import install_entry_mode_intelligence
import live_background
from live_background import run_live_background_job
import search_worker


# The web bootstrap installs the same wrapper for foreground/HTTP generation.
# Background generation imports app directly, so install it here as well before
# the worker loop can interpret its first durable job.
install_entry_mode_intelligence(search_worker.app_module)

# Keep search_worker.main and its heartbeat/shutdown behavior stable. Its runner
# is a module-level callable, so production can switch to the true-live durable
# implementation without duplicating the worker process lifecycle.
search_worker.run_availability_hunter_job = run_live_background_job

# Verification v3 keeps the fast API/RDAP/oEmbed path authoritative and immediate.
# Completed fast rows are then submitted to Browser Eye asynchronously; Chromium,
# WebKit and sparse search corroboration run while the next naming batch proceeds.
install_live_background_enrichment(live_background)


def _telemetry_cleanup_loop():
    # Run immediately, then at most hourly. Short-lived audit and lifecycle rows
    # disappear after their TTL while final candidate/session facts remain durable.
    while not search_worker.STOP.is_set():
        try:
            audit_removed = AUDIT_STORE.prune_expired()
            live_removed = LIVE_CANDIDATES.prune_expired()
            if audit_removed or live_removed:
                print(
                    "NameMachine retention:",
                    f"audit={audit_removed}",
                    f"candidate_events={live_removed}",
                    flush=True,
                )
        except Exception as error:
            print(f"NameMachine telemetry retention failed: {type(error).__name__}", flush=True)
        search_worker.STOP.wait(3600.0)


def main():
    sweeper = threading.Thread(
        target=_telemetry_cleanup_loop,
        name="namemachine-telemetry-retention",
        daemon=True,
    )
    sweeper.start()
    try:
        return search_worker.main()
    finally:
        search_worker.STOP.set()
        sweeper.join(timeout=2.0)
        BROWSER_ENRICHMENT.shutdown(wait=False)


if __name__ == "__main__":
    raise SystemExit(main())