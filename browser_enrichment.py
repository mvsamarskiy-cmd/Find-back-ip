"""Asynchronous Browser Intelligence enrichment for NameMachine.

Fast API/RDAP/oEmbed verification stays on the critical path. Browser evidence is
submitted only after a candidate has already been persisted as a completed fast
result, so Chromium/WebKit/search corroboration can never delay the next naming
batch or the user's live feed.

Browser evidence is deliberately conservative:
- an exact rendered profile can confirm occupancy;
- two independent browser-engine absence observations can strengthen `not_found`;
- browser absence never becomes `claimable`;
- search-engine results are collision corroboration only and never establish
  claimability or occupancy by themselves;
- a browser contradiction against strict `claimable` evidence fails closed to
  `unknown` instead of silently rewriting semantic truth.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import os
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Any

import requests
from sqlalchemy import select, update

from final_ranking import annotate_candidate, strict_availability_state
from identity_bundle import classify_identity_bundle
from session_store import SessionStore, _iso, _utcnow, candidates, evidence


SOCIAL_RESOURCES = ("instagram", "telegram", "tiktok", "youtube", "facebook", "x")
HARD_CONFLICT = frozenset({"taken", "reserved", "invalid"})
ABSENCE_ELIGIBLE = frozenset({"not_found", "unknown", "rate_limited"})

PLATFORM_DOMAINS = {
    "instagram": "instagram.com",
    "telegram": "t.me",
    "tiktok": "tiktok.com",
    "youtube": "youtube.com",
    "facebook": "facebook.com",
    "x": "x.com",
}


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


BROWSER_ENRICH_WORKERS = _bounded_int("BROWSER_ENRICH_WORKERS", 4, 1, 12)
BROWSER_ENRICH_QUEUE = _bounded_int("BROWSER_ENRICH_QUEUE", 32, 4, 256)
BROWSER_RESOURCE_FANOUT = _bounded_int("BROWSER_RESOURCE_FANOUT", 3, 1, 6)
BROWSER_HTTP_TIMEOUT = _bounded_float("BROWSER_EYE_HTTP_TIMEOUT", 6.0, 1.0, 20.0)
BROWSER_MIN_SCORE = _bounded_float("BROWSER_EYE_MIN_SCORE", 50.0, 0.0, 100.0)
BROWSER_SEARCH_MIN_SCORE = _bounded_float("BROWSER_SEARCH_MIN_SCORE", 68.0, 0.0, 100.0)
BROWSER_BREAKER_FAILURES = _bounded_int("BROWSER_EYE_BREAKER_FAILURES", 5, 2, 30)
BROWSER_BREAKER_SECONDS = _bounded_float("BROWSER_EYE_BREAKER_SECONDS", 30.0, 5.0, 300.0)


def browser_enrichment_diagnostics() -> dict[str, Any]:
    url = str(os.environ.get("BROWSER_EYE_URL") or "").strip()
    return {
        "configured": bool(url),
        "mode": "async_post_fast_verification",
        "critical_path_blocking": False,
        "profile_eye_a": "chromium",
        "profile_eye_b": "webkit",
        "search_eye": "google_corroboration",
        "search_can_decide_claimability": False,
        "browser_absence_can_decide_claimability": False,
        "double_absence_promotes_only_to": "not_found",
        "queue_capacity": BROWSER_ENRICH_QUEUE,
        "workers": BROWSER_ENRICH_WORKERS,
    }


def _status(row: Any) -> str:
    return str(row.get("status") or "unknown").lower() if isinstance(row, dict) else "unknown"


def _confidence(row: Any) -> float:
    if not isinstance(row, dict):
        return 0.0
    try:
        value = float(row.get("confidence") or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(1.0, value))


def _eye_signal(row: Any) -> str:
    if not isinstance(row, dict):
        return "unknown"
    signal = str(row.get("signal") or "unknown").lower()
    return signal if signal in {"exists", "absent", "unknown", "rate_limited", "invalid"} else "unknown"


def _compact_eye(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"signal": "unknown", "confidence": 0.0}
    allowed = (
        "signal", "confidence", "engine", "latency_ms", "final_url", "http_status",
        "username", "username_exact", "display_name", "profile_id", "avatar_present",
        "avatar_url", "bio_present", "canonical_url", "canonical_match",
        "login_wall", "challenge", "rate_limited", "network_identity",
    )
    result = {key: row.get(key) for key in allowed if key in row}
    result["signal"] = _eye_signal(row)
    result["confidence"] = _confidence(row)
    return result


def merge_browser_platform(base_row: Any, eye_a: Any = None, eye_b: Any = None, search: Any = None):
    """Merge browser facts into one availability row without inventing freedom."""
    base = dict(base_row or {}) if isinstance(base_row, dict) else {
        "status": "unknown",
        "detail": "No primary verifier result",
        "url": "",
        "source": "browser_eye",
        "method": "browser_enrichment",
        "confidence": 0.0,
        "occupancy": "unknown",
        "claimability": "unconfirmed",
    }
    current = _status(base)
    a = _compact_eye(eye_a)
    b = _compact_eye(eye_b)
    signals = [a.get("signal"), b.get("signal")]
    exists_rows = [row for row in (a, b) if row.get("signal") == "exists"]
    absent_rows = [row for row in (a, b) if row.get("signal") == "absent"]

    search_row = dict(search or {}) if isinstance(search, dict) else {}
    exact_hits = max(0, int(search_row.get("exact_profile_hits") or 0))
    browser_meta = {
        "eye_a": a,
        "eye_b": b,
        "consensus": "unknown",
        "double_checked": bool(eye_a is not None and eye_b is not None),
        "search": {
            "exact_profile_hits": exact_hits,
            "captcha": bool(search_row.get("captcha", False)),
            "latency_ms": search_row.get("latency_ms"),
        } if search_row else {},
    }

    if exists_rows:
        browser_meta["consensus"] = "exists" if len(exists_rows) == 2 else "exists_single_eye"
        best = max(exists_rows, key=lambda row: float(row.get("confidence") or 0.0))
        if current == "claimable":
            # Authoritative free evidence and a rendered exact identity disagree.
            # Never pick the convenient answer: force the candidate back to an
            # unresolved state until another authoritative check settles it.
            merged = dict(base)
            merged.update({
                "status": "unknown",
                "detail": "Browser identity contradicts strict claimability; manual/authoritative recheck required",
                "source": "browser_fusion",
                "method": "claimability_contradiction",
                "confidence": max(_confidence(base), float(best.get("confidence") or 0.0)),
                "occupancy": "unknown",
                "claimability": "unconfirmed",
            })
        elif current in HARD_CONFLICT:
            merged = dict(base)
            merged["confidence"] = max(_confidence(base), float(best.get("confidence") or 0.0))
        else:
            merged = dict(base)
            merged.update({
                "status": "taken",
                "detail": "Rendered browser profile contains an exact identity fingerprint",
                "source": "browser_fusion",
                "method": "rendered_identity",
                "confidence": max(0.9, float(best.get("confidence") or 0.0)),
                "occupancy": "occupied",
                "claimability": "not_claimable",
            })
        return merged, browser_meta

    if len(absent_rows) >= 2:
        browser_meta["consensus"] = "absent_two_engines"
        absence_confidence = min(0.96, max(0.86, sum(float(row.get("confidence") or 0.0) for row in absent_rows) / len(absent_rows)))
        if current in ABSENCE_ELIGIBLE:
            merged = dict(base)
            merged.update({
                "status": "not_found",
                "detail": "Chromium and WebKit independently observed explicit profile absence; claimability remains unconfirmed",
                "source": "browser_fusion",
                "method": "double_engine_absence",
                "confidence": max(_confidence(base), absence_confidence),
                "occupancy": "not_found",
                "claimability": "unconfirmed",
            })
        else:
            # `claimable`, `purchasable`, and hard conflicts retain their stronger
            # semantic status. Browser absence is corroboration only.
            merged = dict(base)
            merged["confidence"] = max(_confidence(base), min(absence_confidence, 0.95))
        return merged, browser_meta

    if len(absent_rows) == 1:
        browser_meta["consensus"] = "absent_single_eye"
    elif any(signal == "rate_limited" for signal in signals):
        browser_meta["consensus"] = "rate_limited"
    return dict(base), browser_meta


def _strict_bundle(row: dict[str, Any], required_resources) -> dict[str, Any]:
    availability = row.get("availability") if isinstance(row.get("availability"), dict) else {}
    required = [str(item) for item in (required_resources or availability.keys()) if str(item) in availability]
    result = classify_identity_bundle(availability, required)
    statuses = {
        resource: _status(availability.get(resource))
        for resource in required
    }
    result.update({
        "bundle_availability_state": strict_availability_state(availability, required),
        "bundle_claimable": [resource for resource, status in statuses.items() if status == "claimable"],
        "bundle_purchasable": [resource for resource, status in statuses.items() if status == "purchasable"],
    })
    return result


def apply_browser_enrichment(row: dict[str, Any], browser_results: dict[str, Any], required_resources=None):
    """Return a new candidate row with browser evidence and refreshed ranking."""
    result = deepcopy(row or {})
    availability = dict(result.get("availability") or {})
    browser_verification = dict(result.get("browser_verification") or {})
    for resource, payload in (browser_results or {}).items():
        if resource not in availability or not isinstance(payload, dict):
            continue
        merged, metadata = merge_browser_platform(
            availability.get(resource),
            payload.get("eye_a"),
            payload.get("eye_b"),
            payload.get("search"),
        )
        availability[resource] = merged
        browser_verification[resource] = metadata

    result["availability"] = availability
    result["browser_verification"] = browser_verification
    result["browser_verification_state"] = "complete"
    result["browser_enriched_at"] = _iso(_utcnow())
    required = list(required_resources or result.get("required_resources") or availability.keys())
    result.update(_strict_bundle(result, required))
    result.update(annotate_candidate(result, required))
    return result


def persist_browser_enrichment(event_store, job, enriched_row, stage="browser_v3"):
    """Durably replace a completed candidate and emit one incremental row event."""
    if not isinstance(enriched_row, dict) or not enriched_row.get("name"):
        return None
    name = "".join(ch for ch in str(enriched_row.get("name") or "") if ch.isascii() and ch.isalpha())[:96]
    key = name.lower()
    if not key:
        return None
    engine = event_store._engine()
    now = _utcnow()
    with engine.begin() as conn:
        existing = conn.execute(
            select(candidates).where(
                (candidates.c.session_id == job["session_id"])
                & (candidates.c.name_key == key)
            )
        ).mappings().one_or_none()
        if existing is None:
            return None
        prior = dict(existing.get("row") or {})
        row = dict(prior)
        row.update(enriched_row)
        row["name"] = name
        row["checked"] = True
        row["verification_state"] = "complete"
        row["received_seq"] = int(existing.get("received_seq") or prior.get("received_seq") or 0)
        row["received_at"] = prior.get("received_at") or _iso(existing.get("received_at")) or _iso(now)
        row["run_id"] = prior.get("run_id") or str(job.get("run_id") or "")[:96]

        conn.execute(
            update(candidates)
            .where(
                (candidates.c.session_id == job["session_id"])
                & (candidates.c.name_key == key)
            )
            .values(row=row, name=name, updated_at=now)
        )

        verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
        for resource, payload in (row.get("availability") or {}).items():
            if not isinstance(payload, dict):
                continue
            resource_key = str(resource)[:32]
            SessionStore._upsert(
                conn,
                evidence,
                (evidence.c.session_id == job["session_id"])
                & (evidence.c.name_key == key)
                & (evidence.c.resource == resource_key),
                {
                    "session_id": job["session_id"],
                    "name_key": key,
                    "resource": resource_key,
                    "availability": payload,
                    "verification": verification.get(resource) if isinstance(verification.get(resource), dict) else None,
                    "updated_at": now,
                },
            )
        event_seq = event_store._emit(
            conn,
            job,
            key,
            "candidate_enriched",
            {"row": row, "stage": stage},
            now,
        )
    output = dict(row)
    output["lifecycle_event_seq"] = event_seq
    return output


class BrowserEnrichmentRuntime:
    """Bounded, non-blocking client for the private Browser Eye service."""

    def __init__(self):
        self._executor = ThreadPoolExecutor(
            max_workers=BROWSER_ENRICH_WORKERS,
            thread_name_prefix="browser-enrichment",
        )
        self._slots = BoundedSemaphore(BROWSER_ENRICH_QUEUE)
        self._lock = Lock()
        self._failures = 0
        self._breaker_until = 0.0
        self._submitted = 0
        self._completed = 0
        self._dropped = 0

    @property
    def base_url(self) -> str:
        return str(os.environ.get("BROWSER_EYE_URL") or "").strip().rstrip("/")

    @property
    def token(self) -> str:
        return str(os.environ.get("BROWSER_EYE_TOKEN") or "").strip()

    def diagnostics(self):
        with self._lock:
            return {
                **browser_enrichment_diagnostics(),
                "submitted": self._submitted,
                "completed": self._completed,
                "dropped_capacity": self._dropped,
                "circuit_open": monotonic() < self._breaker_until,
            }

    def _headers(self):
        headers = {"Content-Type": "application/json", "User-Agent": "NameMachine-browser-client/3"}
        if self.token:
            headers["X-Browser-Eye-Token"] = self.token
        return headers

    def _post(self, path: str, payload: dict[str, Any]):
        response = requests.post(
            self.base_url + path,
            json=payload,
            timeout=BROWSER_HTTP_TIMEOUT,
            headers=self._headers(),
        )
        if response.status_code == 429:
            return {"signal": "rate_limited", "confidence": 0.0, "http_status": 429}
        response.raise_for_status()
        value = response.json()
        return value if isinstance(value, dict) else {"signal": "unknown", "confidence": 0.0}

    def _probe_resource(self, name: str, resource: str, engine: str):
        return self._post("/v1/profile", {"platform": resource, "handle": name, "engine": engine})

    def _search_resource(self, name: str, resource: str):
        domain = PLATFORM_DOMAINS.get(resource)
        if not domain:
            return {}
        query = f'site:{domain} "{name}"'
        return self._post("/v1/search", {"query": query, "handle": name, "platform": resource})

    @staticmethod
    def _candidate_score(row):
        for key in ("final_score", "identity_relevance_score", "name_quality_score", "local_quality_score"):
            try:
                if row.get(key) is not None:
                    return float(row.get(key))
            except (TypeError, ValueError):
                continue
        return 50.0

    def _resources_to_probe(self, job, row):
        availability = row.get("availability") if isinstance(row.get("availability"), dict) else {}
        required = list(job.get("required_resources") or job.get("resources") or [])
        # A required hard conflict already kills the candidate. Spending browser
        # CPU on it cannot improve ranking, so it leaves the expensive pipe early.
        if any(_status(availability.get(resource)) in HARD_CONFLICT for resource in required):
            return []
        score = self._candidate_score(row)
        interesting = score >= BROWSER_MIN_SCORE or any(
            _status(availability.get(resource)) in ABSENCE_ELIGIBLE for resource in required
        )
        if not interesting:
            return []
        return [
            resource for resource in (job.get("resources") or [])
            if resource in SOCIAL_RESOURCES
            and resource in availability
            and _status(availability.get(resource)) not in HARD_CONFLICT
            and _status(availability.get(resource)) != "purchasable"
        ]

    def _parallel_profiles(self, name, resources, engine):
        if not resources:
            return {}
        workers = max(1, min(BROWSER_RESOURCE_FANOUT, len(resources)))
        output = {}
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"browser-{engine}") as executor:
            futures = {
                executor.submit(self._probe_resource, name, resource, engine): resource
                for resource in resources
            }
            for future in as_completed(futures):
                resource = futures[future]
                try:
                    output[resource] = future.result()
                except Exception:
                    output[resource] = {"signal": "unknown", "confidence": 0.0, "engine": engine}
        return output

    def _run(self, job, row, event_store):
        resources = self._resources_to_probe(job, row)
        if not resources:
            return None
        name = str(row.get("name") or "").strip()
        eye_a = self._parallel_profiles(name, resources, "chromium")

        # The second engine is reserved for decisive observations. Unknown/login
        # walls do not deserve another expensive page load; they remain unknown.
        second_resources = [
            resource for resource in resources
            if _eye_signal(eye_a.get(resource)) in {"exists", "absent"}
        ]
        eye_b = self._parallel_profiles(name, second_resources, "webkit")

        results = {}
        score = self._candidate_score(row)
        for resource in resources:
            payload = {"eye_a": eye_a.get(resource)}
            if resource in eye_b:
                payload["eye_b"] = eye_b[resource]
            # Search is last and sparse: only double-absence high-quality candidates
            # need indexed-web collision corroboration. It never determines free/taken.
            if (
                score >= BROWSER_SEARCH_MIN_SCORE
                and _eye_signal(eye_a.get(resource)) == "absent"
                and _eye_signal(eye_b.get(resource)) == "absent"
            ):
                try:
                    payload["search"] = self._search_resource(name, resource)
                except Exception:
                    payload["search"] = {"exact_profile_hits": 0, "error": True}
            results[resource] = payload

        enriched = apply_browser_enrichment(
            row,
            results,
            job.get("required_resources") or job.get("resources") or [],
        )
        persisted = persist_browser_enrichment(event_store, job, enriched)
        with self._lock:
            self._failures = 0
            self._completed += 1
        return persisted

    def _failed(self):
        with self._lock:
            self._failures += 1
            if self._failures >= BROWSER_BREAKER_FAILURES:
                self._breaker_until = monotonic() + BROWSER_BREAKER_SECONDS
                self._failures = 0

    def submit(self, job, row, event_store):
        if not self.base_url or not isinstance(row, dict) or not row.get("name"):
            return False
        with self._lock:
            if monotonic() < self._breaker_until:
                return False
        if not self._slots.acquire(blocking=False):
            with self._lock:
                self._dropped += 1
            return False
        with self._lock:
            self._submitted += 1

        future = self._executor.submit(self._run, dict(job), dict(row), event_store)

        def done(completed):
            try:
                completed.result()
            except Exception:
                self._failed()
            finally:
                self._slots.release()

        future.add_done_callback(done)
        return True

    def shutdown(self, wait=True):
        self._executor.shutdown(wait=wait, cancel_futures=True)


BROWSER_ENRICHMENT = BrowserEnrichmentRuntime()


def install_live_background_enrichment(live_background_module):
    """Submit browser work after fast batch completion without delaying next batch."""
    base = live_background_module._verify_and_finalize
    if getattr(base, "_browser_enrichment_wrapper", False):
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
        for row in completed:
            BROWSER_ENRICHMENT.submit(job, row, live_background_module.LIVE_CANDIDATES)
        return completed

    wrapped._browser_enrichment_wrapper = True
    live_background_module._verify_and_finalize = wrapped


__all__ = [
    "BROWSER_ENRICHMENT",
    "BrowserEnrichmentRuntime",
    "apply_browser_enrichment",
    "browser_enrichment_diagnostics",
    "install_live_background_enrichment",
    "merge_browser_platform",
    "persist_browser_enrichment",
]
