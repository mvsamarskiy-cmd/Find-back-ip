"""Opt-in one-shot smoke for the full private Opportunity Intelligence pipeline.

The probe runs a fixed non-user query and emits only aggregate, non-sensitive
metrics. It never logs secrets, result titles, URLs, descriptions, page text, or
query text. Disabled by default.
"""
from __future__ import annotations

import json
import os
from threading import Thread
from time import perf_counter, sleep


SMOKE_FLAG = "OPPORTUNITY_PIPELINE_STARTUP_SMOKE"
SMOKE_MARKER = "OPPORTUNITY_PIPELINE_SMOKE"


def _enabled() -> bool:
    return str(os.environ.get(SMOKE_FLAG) or "").strip().lower() in {"1", "true", "yes", "on"}


def summarize_pipeline_payload(payload, *, duration_ms=None):
    value = payload if isinstance(payload, dict) else {}
    rows = [row for row in (value.get("results") or []) if isinstance(row, dict)]
    normalized = [row for row in rows if row.get("normalized") is True]
    official = [row for row in rows if row.get("official_source")]
    source_verified = [
        row for row in rows
        if ((row.get("opportunity") or {}).get("verification") or {}).get("source_verified")
    ]
    statuses = {}
    with_amount = 0
    with_deadline = 0
    fit_scores = []
    for row in rows:
        opportunity = row.get("opportunity") if isinstance(row.get("opportunity"), dict) else {}
        status = opportunity.get("status") if isinstance(opportunity.get("status"), dict) else {}
        key = str(status.get("value") or "unknown")[:40]
        statuses[key] = statuses.get(key, 0) + 1
        if isinstance(opportunity.get("amount"), dict):
            with_amount += 1
        if isinstance(opportunity.get("deadline"), dict):
            with_deadline += 1
        fit = row.get("fit") if isinstance(row.get("fit"), dict) else {}
        try:
            fit_scores.append(int(fit.get("score")))
        except (TypeError, ValueError):
            pass
    return {
        "provider_status": str(value.get("provider_status") or "unknown")[:80],
        "requested_category": str(value.get("requested_category") or "")[:40] or None,
        "routed_category": str(value.get("routed_category") or "")[:40] or None,
        "intent_routed": bool(value.get("intent_routed")),
        "intelligence_version": str(value.get("intelligence_version") or "")[:40] or None,
        "result_count": len(rows),
        "normalized_count": len(normalized),
        "official_source_count": len(official),
        "source_verified_count": len(source_verified),
        "with_amount_count": with_amount,
        "with_deadline_count": with_deadline,
        "status_counts": statuses,
        "top_fit_score": max(fit_scores) if fit_scores else None,
        "duration_ms": int(duration_ms) if duration_ms is not None else None,
    }


def run_pipeline_smoke(*, searcher=None):
    if searcher is None:
        from opportunity_search import search_global as searcher
    started = perf_counter()
    try:
        payload = searcher(
            "AI grants for startups",
            category="all",
            country="PL",
        )
        return summarize_pipeline_payload(
            payload,
            duration_ms=int((perf_counter() - started) * 1000),
        )
    except Exception as error:
        return {
            "provider_status": "pipeline_error",
            "requested_category": "all",
            "routed_category": None,
            "intent_routed": False,
            "intelligence_version": None,
            "result_count": 0,
            "normalized_count": 0,
            "official_source_count": 0,
            "source_verified_count": 0,
            "with_amount_count": 0,
            "with_deadline_count": 0,
            "status_counts": {},
            "top_fit_score": None,
            "duration_ms": int((perf_counter() - started) * 1000),
            "error_type": type(error).__name__,
        }


def _background_probe():
    sleep(1.4)
    result = run_pipeline_smoke()
    print(f"{SMOKE_MARKER} {json.dumps(result, ensure_ascii=True, separators=(',', ':'))}", flush=True)


def maybe_start_pipeline_smoke() -> bool:
    if not _enabled():
        return False
    Thread(target=_background_probe, name="opportunity-pipeline-smoke", daemon=True).start()
    return True


__all__ = [
    "SMOKE_FLAG", "SMOKE_MARKER", "maybe_start_pipeline_smoke",
    "run_pipeline_smoke", "summarize_pipeline_payload",
]
