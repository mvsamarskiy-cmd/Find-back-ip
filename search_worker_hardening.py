"""Production hardening for the long-running naming/search loop.

The durable worker must learn from feedback for the *current search intent* without
letting unrelated names from older prompts steer a new job. It also must not die
before checking a single candidate merely because the background service is
missing an AI credential: the foreground remains GPT-first, while the worker has a
bounded local fallback so a large search can still make progress and expose facts.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any

from sqlalchemy import select, update

from background_jobs import search_jobs
from candidate_funnel import expand_local_families, lexical_seeds
from creative_lexicon import creative_palette
from session_store import _iso, _utcnow, candidates, feedback, runs, sessions


HARD_CONFLICT = {"taken", "reserved", "invalid"}
POSITIVE_HINT = {"claimable", "purchasable", "not_found"}


def _norm_prompt(value: Any) -> str:
    return " ".join(re.findall(r"[\w]+", str(value or "").lower(), flags=re.UNICODE))[:600]


def same_intent(left: Any, right: Any) -> bool:
    """Conservative intent equivalence used only to scope feedback memory."""
    a, b = _norm_prompt(left), _norm_prompt(right)
    if not a or not b:
        return False
    if a == b:
        return True
    if min(len(a), len(b)) < 6:
        return False
    ratio = SequenceMatcher(None, a, b).ratio()
    a_tokens, b_tokens = set(a.split()), set(b.split())
    union = a_tokens | b_tokens
    overlap = len(a_tokens & b_tokens) / len(union) if union else 0.0
    return ratio >= 0.84 or (ratio >= 0.72 and overlap >= 0.72)


def _vote(value: Any) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return 0
    return 1 if value > 0 else -1 if value < 0 else 0


def _row_conflict(row: dict[str, Any]) -> bool:
    if str(row.get("bundle_state") or "") == "conflict":
        return True
    availability = row.get("availability") if isinstance(row.get("availability"), dict) else {}
    return any(
        isinstance(payload, dict) and str(payload.get("status") or "unknown") in HARD_CONFLICT
        for payload in availability.values()
    )


def _row_opportunity(row: dict[str, Any]) -> bool:
    if _row_conflict(row):
        return False
    availability = row.get("availability") if isinstance(row.get("availability"), dict) else {}
    statuses = {
        str(payload.get("status") or "unknown")
        for payload in availability.values()
        if isinstance(payload, dict)
    }
    return str(row.get("bundle_state") or "") in {"confirmed", "promising"} or bool(statuses & POSITIVE_HINT)


def _run_prompt(payload: Any) -> str:
    return str(payload.get("prompt") or "") if isinstance(payload, dict) else ""


def _intent_snapshot(module, job):
    """Read only rows whose originating run matches the current job intent."""
    engine = module.JOB_STORE.session_store._ensure_engine()
    session_id = str(job.get("session_id") or "")
    run_id = str(job.get("run_id") or "")
    prompt = str(job.get("prompt") or "")
    with engine.connect() as conn:
        run_rows = conn.execute(
            select(runs.c.run_id, runs.c.payload).where(runs.c.session_id == session_id)
        ).mappings().all()
        matching_run_ids = {
            str(item.get("run_id") or "")
            for item in run_rows
            if str(item.get("run_id") or "") and same_intent(_run_prompt(item.get("payload")), prompt)
        }
        if run_id:
            matching_run_ids.add(run_id)

        stmt = (
            select(candidates.c.name_key, candidates.c.row, candidates.c.run_id)
            .where(candidates.c.session_id == session_id)
            .order_by(candidates.c.received_seq.desc(), candidates.c.updated_at.desc())
            .limit(260)
        )
        candidate_rows = conn.execute(stmt).mappings().all()
        recent_rows = [
            item for item in candidate_rows
            if str(item.get("run_id") or "") in matching_run_ids
        ][:180]
        name_keys = {str(item.get("name_key") or "").lower() for item in recent_rows}

        feedback_rows = conn.execute(
            select(feedback.c.name_key, feedback.c.payload, feedback.c.updated_at)
            .where(feedback.c.session_id == session_id)
            .order_by(feedback.c.updated_at.asc())
        ).mappings().all()
        feedback_rows = [
            item for item in feedback_rows
            if str(item.get("name_key") or "").lower() in name_keys
        ]
        session_row = conn.execute(
            select(sessions.c.shortlist, sessions.c.direction_anchors).where(sessions.c.id == session_id)
        ).mappings().one_or_none()

    return matching_run_ids, recent_rows, feedback_rows, session_row


def _scoped_runtime_state(module, job, generation_context):
    base_preferences = dict(job.get("preferences") or {})
    context = dict(generation_context or {})
    matching_run_ids, recent_rows, feedback_rows, session_row = _intent_snapshot(module, job)

    recent = [dict(item.get("row") or {}) for item in recent_rows if isinstance(item.get("row"), dict)]
    by_key = {
        str(item.get("name_key") or "").lower(): dict(item.get("row") or {})
        for item in recent_rows
        if isinstance(item.get("row"), dict)
    }

    feedback_items = []
    liked, disliked = [], []
    latest_feedback_at = None
    for item in feedback_rows:
        key = str(item.get("name_key") or "").lower()
        row = by_key.get(key, {})
        payload = dict(item.get("payload") or {})
        name = str(row.get("name") or key)
        vote = _vote(payload.get("vote"))
        comment = " ".join(str(payload.get("comment") or "").split())[:300]
        family = str(row.get("family") or payload.get("family") or "unknown")[:30]
        feedback_items.append({"name": name, "vote": vote, "comment": comment, "family": family})
        if vote > 0:
            liked.append(name)
        elif vote < 0:
            disliked.append(name)
        if item.get("updated_at"):
            latest_feedback_at = _iso(item.get("updated_at"))

    # Explicit shortlist/direction choices remain powerful, but only if that name
    # belongs to a run with the same intent. This prevents an old floral search,
    # for example, from becoming hard guidance for a new "boom"-style search.
    allowed_names = set(by_key)
    shortlist = [
        str(value) for value in (session_row.get("shortlist") or [])
        if str(value).lower() in allowed_names
    ] if session_row else []
    anchors = [
        str(value) for value in (session_row.get("direction_anchors") or [])
        if str(value).lower() in allowed_names
    ] if session_row else []

    preferences = {
        "liked": liked[-20:],
        "disliked": disliked[-20:],
        "reasons": dict(base_preferences.get("reasons") or {}),
    }
    if feedback_items:
        preferences["feedback"] = feedback_items[-80:]
    if anchors:
        preferences["direction_anchors"] = anchors[-20:]
    if shortlist:
        preferences["shortlist"] = shortlist[-20:]

    recent_names = [str(row.get("name") or "") for row in recent if row.get("name")]
    conflict_names = [str(row.get("name") or "") for row in recent if row.get("name") and _row_conflict(row)]
    opportunity_names = [str(row.get("name") or "") for row in recent if row.get("name") and _row_opportunity(row)]
    directional = []
    seen = set()
    for name in [*anchors, *shortlist, *liked, *opportunity_names]:
        key = str(name).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        directional.append(str(name).strip())

    context["exclude_names"] = recent_names[:100]
    context["conflict_names"] = conflict_names[:40]
    context["successful_names"] = directional[:20]

    runtime = {
        "applied_at": _iso(_utcnow()),
        "applied_batch": int(job.get("attempted_batches") or 0) + 1,
        "intent_scope": "matching_prompt_runs",
        "intent_run_count": len(matching_run_ids),
        "feedback_count": len(feedback_items),
        "liked_count": len(liked),
        "disliked_count": len(disliked),
        "latest_feedback_at": latest_feedback_at,
        "conflict_examples": len(context["conflict_names"]),
        "opportunity_examples": len(context["successful_names"]),
    }
    preferences["_runtime"] = runtime

    engine = module.JOB_STORE.session_store._ensure_engine()
    with engine.begin() as conn:
        conn.execute(
            update(search_jobs)
            .where(search_jobs.c.id == job.get("id"))
            .values(preferences=preferences, updated_at=_utcnow())
        )
    job["preferences"] = preferences
    return preferences, context, runtime


def _strip_stale_anchor_guidance(search_context: Any) -> dict[str, Any]:
    context = dict(search_context or {})
    guidance = " ".join(str(context.get("guidance") or "").split())
    # Keep mode locks and other explicit rules, but exact name anchors are supplied
    # again through the intent-scoped preferences above.
    guidance = re.sub(r"(?:\s*\|\s*)?Орієнтуйся на:\s*[^|]+", "", guidance, flags=re.I)
    guidance = re.sub(r"(?:\s*\|\s*)?Use as direction:\s*[^|]+", "", guidance, flags=re.I)
    context["guidance"] = guidance.strip(" |")[:500]
    return context


def _fallback_pool(module, brief, count, brand_dna, search_context, generation_context):
    """Bounded deterministic fallback used only when model generation is unavailable."""
    adaptive = dict(generation_context or {})
    batch_number = int(adaptive.get("batch_number") or 1)
    palette = creative_palette(
        brief,
        brand_dna,
        (search_context or {}).get("guidance", "") if isinstance(search_context, dict) else "",
        batch_number=batch_number,
        forbidden=set(getattr(module.app_module, "BANNED_ROOTS", ())) | set(getattr(module.app_module, "BANNED_SUFFIXES", ())),
    )
    dna = dict(brand_dna or {}) if isinstance(brand_dna, dict) else {}
    seeds = lexical_seeds(brief, brand_dna, limit=12)
    roots = []
    for value in [*seeds, *(palette.get("local_roots") or [])]:
        clean = re.sub(r"[^a-z]", "", str(value).lower())
        if 3 <= len(clean) <= 14 and clean not in roots:
            roots.append(clean)
    if roots:
        dna["keywords"] = list(dna.get("keywords") or [])[:8] + roots[:14]

    pool = expand_local_families(brief, dna, limit=180)
    # A one-word/style-only brief can legitimately yield too few semantic roots.
    # Fill the fallback pool with the legacy phonetic generator. Selection below
    # still enforces spelling, blacklist, near-duplicate and local-quality gates.
    needed_raw = max(160, count * 14)
    seen = {str(row.get("name") or "").lower() for row in pool}
    attempts = 0
    while len(pool) < needed_raw and attempts < needed_raw * 40:
        attempts += 1
        name = module.app_module.candidate()
        key = str(name).lower()
        if key in seen:
            continue
        seen.add(key)
        pool.append({
            "name": name,
            "family": "invented_phonetic",
            "reason": "Резервний локальний генератор зберіг пошук активним, поки AI-провайдер недоступний.",
            "pronunciation": name,
            "language_risks": [],
            "candidate_source": "local_resilient_fallback",
        })
    return pool


def _fallback_select(ai_engine, pool, count, search_context, exclude_names):
    """Fill a full fallback batch without weakening normal validity/diversity gates.

    Normal MMR intentionally caps each naming family. A degraded one-word fallback
    can be mostly invented-phonetic, so applying the family cap as a hard limit can
    return five names for a requested batch of twenty and recreate the 0/N worker
    failure. We run normal MMR first, then fill only with individually valid,
    non-near-duplicate rows ranked by the existing local quality model.
    """
    selected = list(ai_engine.select_diverse_names(
        pool,
        count,
        search_context,
        exclude_names=exclude_names,
    ))
    if len(selected) >= count:
        return selected[:count]

    blocked = [str(value) for value in (exclude_names or []) if str(value)]
    blocked.extend(str(row.get("name") or "") for row in selected)
    chosen = {str(row.get("name") or "").lower() for row in selected}
    for candidate in ai_engine.rank_candidate_pool(pool):
        name = str(candidate.get("name") or "").strip()
        key = name.lower()
        if not key or key in chosen:
            continue
        if not ai_engine._is_allowed_name(name, search_context):
            continue
        if any(ai_engine._too_similar(name, old) for old in blocked):
            continue
        row = dict(candidate)
        row["name"] = name
        selected.append(row)
        chosen.add(key)
        blocked.append(name)
        if len(selected) >= count:
            break
    return selected


def _fallback_generate(module, job, count, generation_context, error):
    import ai_engine

    search_context = _strip_stale_anchor_guidance(job.get("search_context"))
    pool = _fallback_pool(
        module,
        str(job.get("prompt") or ""),
        count,
        job.get("brand_dna"),
        search_context,
        generation_context,
    )
    selected = _fallback_select(
        ai_engine,
        pool,
        count,
        search_context,
        (generation_context or {}).get("exclude_names") or [],
    )
    if len(selected) < count:
        raise error
    for row in selected:
        row["generation_source"] = "local_resilient_fallback"
        row["generation_fallback_reason"] = type(error).__name__
    return selected


def _patch_browser_compaction() -> None:
    """Keep exact-identity audit fields in the durable Browser Eye evidence."""
    try:
        import browser_enrichment
    except Exception:
        return
    base = browser_enrichment._compact_eye
    if getattr(base, "_identity_audit_wrapper", False):
        return

    def compact(row):
        result = base(row)
        if isinstance(row, dict):
            for key in ("requested_handle", "observed_username", "identity_sources", "identity_gate", "final_url_match"):
                if key in row:
                    result[key] = row.get(key)
        return result

    compact._identity_audit_wrapper = True
    browser_enrichment._compact_eye = compact


def install_search_worker_hardening(module) -> None:
    """Patch the already-imported worker module before its loop starts."""
    if getattr(module, "_search_loop_hardened", False):
        return
    original_generate_batch = module.generate_batch

    def runtime_state(job, generation_context):
        return _scoped_runtime_state(module, job, generation_context)

    def generate_batch(job, count, generation_context):
        scoped_job = dict(job or {})
        scoped_job["search_context"] = _strip_stale_anchor_guidance(scoped_job.get("search_context"))
        try:
            rows = original_generate_batch(scoped_job, count, generation_context)
            for row in rows or []:
                if isinstance(row, dict):
                    row.setdefault("generation_source", "gpt")
            return rows
        except Exception as error:
            print(
                f"NameMachine model generation degraded to local fallback: {type(error).__name__}",
                flush=True,
            )
            return _fallback_generate(module, scoped_job, count, generation_context, error)

    module._runtime_generation_state = runtime_state
    module.generate_batch = generate_batch
    module._search_loop_hardened = True
    _patch_browser_compaction()


__all__ = ["install_search_worker_hardening", "same_intent"]
