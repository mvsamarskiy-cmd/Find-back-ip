"""Worker-side bridge for the durable Browser Intelligence pipe.

Foreground streaming persists candidates asynchronously through session_sync;
background searches persist them directly. Both paths enqueue the same durable
browser job, and a small fixed number of pump threads execute the expensive
Browser Eye stages independently from generation/search threads.
"""
from __future__ import annotations

import os

from browser_queue import BROWSER_JOBS, run_queue_pump


def _bounded_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


BROWSER_PIPELINE_WORKERS = _bounded_int("BROWSER_PIPELINE_WORKERS", 3, 1, 8)


class SynchronousBrowserRuntimeAdapter:
    """Adapt one queue-pump thread to the existing BrowserEnrichmentRuntime.

    `BrowserEnrichmentRuntime._run` already parallelizes resources and talks to the
    private service. Running it synchronously inside each dedicated pump thread
    gives us fixed candidate-level concurrency without occupying Gunicorn/search
    threads or adding another in-memory queue ahead of the durable SQL queue.
    """

    def __init__(self, runtime):
        self.runtime = runtime

    def submit(self, job, row, event_store, on_done=None):
        if not self.runtime.base_url:
            return False
        try:
            result = self.runtime._run(dict(job), dict(row), event_store)
        except Exception as error:
            self.runtime._failed()
            if on_done:
                on_done(False, error)
            return True
        if on_done:
            on_done(bool(result), None if result else RuntimeError("Browser candidate was not enriched"))
        return True


def install_live_background_queue(live_background_module, queue=BROWSER_JOBS):
    """Enqueue background completions instead of browser-verifying inline."""
    base = live_background_module._verify_and_finalize
    if getattr(base, "_browser_durable_queue_wrapper", False):
        return

    def wrapped(store, job, staged, batch_number, verify_candidate, verify_workers):
        completed = base(
            store,
            job,
            staged,
            batch_number,
            verify_candidate,
            verify_workers,
        )
        if completed:
            try:
                queue.enqueue_rows(job["session_id"], completed)
            except Exception as error:
                print(
                    f"NameMachine browser enqueue failed: {type(error).__name__}",
                    flush=True,
                )
        return completed

    wrapped._browser_durable_queue_wrapper = True
    live_background_module._verify_and_finalize = wrapped


def pump_main(stop_event, runtime, event_store, worker_id):
    adapter = SynchronousBrowserRuntimeAdapter(runtime)
    run_queue_pump(stop_event, adapter, event_store, worker_id=worker_id)


__all__ = [
    "BROWSER_PIPELINE_WORKERS",
    "SynchronousBrowserRuntimeAdapter",
    "install_live_background_queue",
    "pump_main",
]
