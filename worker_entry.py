"""Production worker entrypoint with short-lived telemetry cleanup."""

from __future__ import annotations

import threading

from session_store_threadsafe import install_threadsafe_session_store


# Search, retention, and Browser Intelligence start concurrently in this process.
# Serialize the one-time lazy SQLAlchemy engine/schema initialization before any
# of those modules can race on PostgreSQL catalog creation.
install_threadsafe_session_store()

from audit_store import AUDIT_STORE
import ai_engine as ai_engine_module
from browser_enrichment import BROWSER_ENRICHMENT
from browser_pipeline_worker import (
    BROWSER_PIPELINE_WORKERS,
    install_live_background_queue,
    pump_main,
)
from creative_generation import install_creative_generation
from durable_candidate_events import LIVE_CANDIDATES
from entry_mode_backend import install_entry_mode_intelligence
import live_background
from live_background import run_live_background_job
import search_worker
from search_worker_hardening import install_search_worker_hardening
from strict_claimability import install_strict_claimability


# app.py imports the generator by value, so install the creative overlay in both
# ai_engine and the worker's app module before the first job can generate a batch.
# Retrieval is local/deterministic and adds no network or extra model call.
install_creative_generation(ai_engine_module, search_worker.app_module)

# The web bootstrap installs the same wrapper for foreground/HTTP generation.
# Background generation imports app directly, so install it here as well before
# the worker loop can interpret its first durable job.
install_entry_mode_intelligence(search_worker.app_module)

# Scope live feedback to the current search intent, strip stale hard anchors, keep
# exact Browser Eye identity evidence, and provide a bounded local generation
# fallback so a missing/transient AI provider cannot fail a 5k search at 0/5000.
install_search_worker_hardening(search_worker)

# Keep search_worker.main and its heartbeat/shutdown behavior stable. Its runner
# is a module-level callable, so production can switch to the true-live durable
# implementation without duplicating the worker process lifecycle.
search_worker.run_availability_hunter_job = run_live_background_job

# Verification v4 keeps public/API/browser checks fast and lets only the sparse
# authoritative claimability stage turn a candidate strict green. Installing this
# before queue workers start also expands queue admission for strict-only .com or
# Telegram work when a corresponding provider is configured.
install_strict_claimability()

# Verification v3.1+ uses one durable Browser Intelligence queue for both search
# modes. The fast verifier persists first; browser and strict claimability work
# are queued after that boundary and therefore never block generation, NDJSON
# delivery, or the next background batch.
install_live_background_queue(live_background)


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

    browser_threads = []
    for index in range(BROWSER_PIPELINE_WORKERS):
        thread = threading.Thread(
            target=pump_main,
            args=(
                search_worker.STOP,
                BROWSER_ENRICHMENT,
                LIVE_CANDIDATES,
                f"browser-pump-{index + 1}",
            ),
            name=f"namemachine-browser-pump-{index + 1}",
            daemon=True,
        )
        thread.start()
        browser_threads.append(thread)

    try:
        return search_worker.main()
    finally:
        search_worker.STOP.set()
        sweeper.join(timeout=2.0)
        for thread in browser_threads:
            thread.join(timeout=2.0)
        BROWSER_ENRICHMENT.shutdown(wait=False)


if __name__ == "__main__":
    raise SystemExit(main())