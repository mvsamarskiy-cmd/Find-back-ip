"""NameMachine durable background search worker.

Run this as a separate process/service, for example `python search_worker.py`.
It never needs a user's plaintext session token: authorization is performed when
the web API enqueues the job, while the worker is a trusted server-side process.
"""

from __future__ import annotations

import os
import signal
import socket
import threading

from telegram_integration import install


install()

import app as app_module  # noqa: E402
from availability_v2 import check_all as check_all_v2  # noqa: E402
from background_jobs import JOB_STORE, run_one_job  # noqa: E402
from streaming_search import _generate_candidates  # noqa: E402


STOP = threading.Event()


def _bounded_float(name, default, minimum, maximum):
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _worker_id():
    configured = str(os.environ.get("NAMEMACHINE_WORKER_ID") or "").strip()
    if configured:
        return configured[:96]
    return f"{socket.gethostname()}-{os.getpid()}"[:96]


def generate_batch(job, count, generation_context):
    brief = job.get("prompt") or ""
    search_context = job.get("search_context") or {}
    resources = job.get("resources") or []
    if os.environ.get("OPENAI_API_KEY"):
        brief, search_context, _intelligence = app_module.apply_prompt_intelligence(
            brief,
            resources,
            search_context,
        )
    data = {"preferences": job.get("preferences") or {}}
    return _generate_candidates(
        app_module,
        brief,
        count,
        data,
        job.get("brand_dna"),
        search_context,
        generation_context,
    )


def verify_candidate(job, candidate):
    result = dict(candidate or {})
    name = str(result.get("name") or "").strip()
    if not name:
        raise ValueError("Candidate has no name")
    checked = check_all_v2(name, resources=job.get("resources") or [])
    result.update(checked)
    result.update(
        app_module.classify_identity_bundle(
            result.get("availability"),
            job.get("required_resources") or job.get("resources") or [],
        )
    )
    result["trademark"] = app_module.trademark_links(name)
    result["checked"] = True
    return result


def _request_stop(*_args):
    STOP.set()


def main():
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    if not JOB_STORE.configured:
        print("NameMachine background worker: database is not configured.", flush=True)
        return 2
    if not JOB_STORE.session_store.ensure_ready():
        print("NameMachine background worker: database is not reachable.", flush=True)
        return 3

    worker_id = _worker_id()
    idle_seconds = _bounded_float("BACKGROUND_WORKER_IDLE_SECONDS", 2.0, 0.25, 30.0)
    print(f"NameMachine background worker started: {worker_id}", flush=True)

    while not STOP.is_set():
        result = run_one_job(
            JOB_STORE,
            worker_id,
            generate_batch,
            verify_candidate,
            should_stop=STOP.is_set,
        )
        if result is None:
            STOP.wait(idle_seconds)
        else:
            print(
                "background job",
                result.get("id"),
                result.get("state"),
                f"{result.get('delivered_count', 0)}/{result.get('target_count', 0)}",
                result.get("stop_reason") or "",
                flush=True,
            )

    print("NameMachine background worker stopped.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
