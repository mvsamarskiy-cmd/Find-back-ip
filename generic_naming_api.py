"""Standalone naming workflow for non-brand tasks.

This endpoint intentionally performs no domain/social/company/trademark lookup.
It is for users who simply want a name, nickname, project title, bot name, game
handle idea, character name, or another naming concept.
"""
from __future__ import annotations

import json
import math
import os
import re
from difflib import SequenceMatcher

from candidate_funnel import rank_candidate_pool
from preference_engine import (
    build_taste_model,
    candidate_preference_score,
    family_allocation,
)


GENERIC_FAMILIES = (
    "semantic_compound",
    "evocative_metaphor",
    "root_blend",
    "invented_phonetic",
    "abstract",
)
GENERIC_SCHEMA = {
    "type": "object",
    "properties": {
        "names": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "family": {"type": "string", "enum": list(GENERIC_FAMILIES)},
                    "reason": {"type": "string"},
                    "pronunciation": {"type": "string"},
                    "language_risks": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "family", "reason", "pronunciation", "language_risks"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["names"],
    "additionalProperties": False,
}
GENERIC_INSTRUCTIONS = """You are a professional naming specialist for arbitrary entities, not only brands.
The user may want a nickname, channel name, project name, bot name, character name,
game identity, object name, product codename, or another type of name. Infer the
entity from the brief and generate names for exactly that entity. Do not assume a
commercial brand unless the user asks for one. Respect the user's likes, dislikes,
comments, and explicit constraints. Prefer memorable, pronounceable, intentional
names over random strings and trivial one-letter mutations. Candidate names in
this release must use ASCII Latin letters A-Z only; no spaces, punctuation,
digits, diacritics, or Cyrillic. Never claim that a name, username, domain,
company, or trademark is available. Explain candidates in Ukrainian."""


def _clean_name(value):
    return re.sub(r"[^A-Za-z]", "", str(value or ""))[:30]


def _clean_rows(rows, limit, excluded):
    output = []
    seen = set(excluded)
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        name = _clean_name(raw.get("name"))
        key = name.lower()
        if len(name) < 3 or key in seen:
            continue
        family = str(raw.get("family") or "abstract")
        if family not in GENERIC_FAMILIES:
            family = "abstract"
        seen.add(key)
        output.append({
            "name": name,
            "family": family,
            "reason": " ".join(str(raw.get("reason") or "").split())[:500],
            "pronunciation": " ".join(str(raw.get("pronunciation") or "").split())[:120],
            "language_risks": [
                " ".join(str(item).split())[:160]
                for item in (raw.get("language_risks") or [])[:8]
                if str(item).strip()
            ],
            "checked": False,
            "product_mode": "generic_name",
        })
        if len(output) >= limit:
            break
    return output


def _taste_model_from_preferences(preferences):
    if not isinstance(preferences, dict):
        return build_taste_model()
    feedback = {}
    candidate_rows = []
    rows = preferences.get("feedback", [])
    if isinstance(rows, list):
        for row in rows[:80]:
            if not isinstance(row, dict):
                continue
            name = _clean_name(row.get("name"))
            if not name:
                continue
            feedback[name] = {
                "vote": row.get("vote", 0),
                "comment": str(row.get("comment", ""))[:300],
            }
            candidate_rows.append({"name": name, "family": row.get("family", "unknown")})
    for name in preferences.get("liked", []) if isinstance(preferences.get("liked"), list) else []:
        clean = _clean_name(name)
        if clean:
            feedback.setdefault(clean, {"vote": 1, "comment": ""})
    for name in preferences.get("disliked", []) if isinstance(preferences.get("disliked"), list) else []:
        clean = _clean_name(name)
        if clean:
            feedback.setdefault(clean, {"vote": -1, "comment": ""})
    return build_taste_model(
        feedback,
        candidate_rows,
        preferences.get("direction_anchors", []),
        preferences.get("shortlist", []),
    )


def _similarity(left, right):
    a = _clean_name(left.get("name", "")).lower()
    b = _clean_name(right.get("name", "")).lower()
    if not a or not b:
        return 0.0
    score = SequenceMatcher(None, a, b).ratio()
    if left.get("family") == right.get("family"):
        score = min(1.0, score + 0.08)
    return score


def _preference_core(rows, confidence, position, count):
    """Keep low-fit exploration out of the high-confidence recommendation core.

    Diversity is still useful, but after explicit feedback it must not pull a
    clearly disliked naming style ahead of candidates that match the learned
    direction. The tail of the batch remains free to explore other families.
    """
    if confidence < 0.25 or not rows:
        return rows
    exploit_slots = min(count, max(1, math.ceil(count * (0.70 + 0.15 * confidence))))
    if position >= exploit_slots:
        return rows
    best_fit = max(float(row.get("user_fit_score", 50.0)) for row in rows)
    tolerance = max(6.0, 14.0 * (1.0 - confidence))
    core = [
        row for row in rows
        if float(row.get("user_fit_score", 50.0)) >= best_fit - tolerance
    ]
    return core or rows


def _select_generic_rows(rows, count, taste_model):
    """Rank by name quality + learned taste, then diversify with MMR.

    Generic naming deliberately does not use brand blacklists or availability
    evidence. It does share the same session-learning principle as verified
    naming so Continue reacts to likes, dislikes, comments and direction anchors.
    Explicit taste evidence defines a recommendation core; MMR explores inside
    that core first and only spends the tail of the batch on weaker-fit families.
    """
    model = taste_model if isinstance(taste_model, dict) else build_taste_model()
    confidence = float(model.get("confidence", 0.0) or 0.0)
    shares = family_allocation(count, model)
    hard_cap = max(2, math.ceil(max(1, count) / 3))
    family_caps = {
        family: min(hard_cap, max(2, math.ceil(shares.get(family, 0.2) * count) + 1))
        for family in GENERIC_FAMILIES
    }
    family_counts = {family: 0 for family in GENERIC_FAMILIES}

    eligible = []
    for row in rank_candidate_pool(rows):
        clean = dict(row)
        fit = candidate_preference_score(clean, model)
        quality = float(clean.get("local_quality_score", 0) or 0)
        user_weight = 0.45 * confidence
        clean["user_fit_score"] = fit
        clean["adaptive_relevance_score"] = round(
            quality * (1.0 - user_weight) + fit * user_weight,
            1,
        )
        eligible.append(clean)

    selected = []
    remaining = eligible[:]
    while remaining and len(selected) < count:
        allowed = [
            candidate for candidate in remaining
            if family_counts.get(str(candidate.get("family", "abstract")), 0)
            < family_caps.get(str(candidate.get("family", "abstract")), hard_cap)
        ]
        if not allowed:
            break
        candidates = _preference_core(allowed, confidence, len(selected), count)
        best = None
        best_score = -10.0
        for candidate in candidates:
            relevance = float(candidate.get("adaptive_relevance_score", 0.0)) / 100.0
            redundancy = max((_similarity(candidate, other) for other in selected), default=0.0)
            mmr = 0.72 * relevance - 0.28 * redundancy
            if mmr > best_score:
                best_score = mmr
                best = candidate
        if best is None:
            break
        remaining.remove(best)
        family = str(best.get("family", "abstract"))
        family_counts[family] = family_counts.get(family, 0) + 1
        selected.append(best)

    # A model can occasionally ignore the requested family mix. Family caps are
    # therefore a diversity preference, not a reason to fail a usable response.
    if len(selected) < count:
        selected_names = {str(row.get("name", "")).lower() for row in selected}
        leftovers = [row for row in eligible if str(row.get("name", "")).lower() not in selected_names]
        leftovers.sort(key=lambda row: float(row.get("adaptive_relevance_score", 0.0)), reverse=True)
        selected.extend(leftovers[: count - len(selected)])
    return selected[:count]


def generate_generic_names(brief, count, preferences=None, generation_context=None):
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    preferences = preferences if isinstance(preferences, dict) else {}
    generation_context = generation_context if isinstance(generation_context, dict) else {}
    excluded = {
        _clean_name(name).lower()
        for name in generation_context.get("exclude_names", [])[:120]
        if _clean_name(name)
    }
    pool_size = min(40, max(count + 8, count * 2))
    client = OpenAI()
    response = client.responses.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
        instructions=GENERIC_INSTRUCTIONS,
        input=(
            f"Generate {pool_size} distinct candidates so at least {count} survive filtering.\n"
            f"USER BRIEF:\n{brief}\n\n"
            f"SESSION FEEDBACK:\n{json.dumps(preferences, ensure_ascii=False)[:5000]}\n\n"
            f"DO NOT REPEAT:\n{json.dumps(sorted(excluded), ensure_ascii=False)[:3000]}"
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "generic_names",
                "strict": True,
                "schema": GENERIC_SCHEMA,
            }
        },
        store=False,
    )
    payload = json.loads(response.output_text)
    pool = _clean_rows(payload.get("names"), pool_size, excluded)
    taste_model = _taste_model_from_preferences(preferences)
    rows = _select_generic_rows(pool, count, taste_model)
    if len(rows) < count:
        raise ValueError(f"Generic naming produced only {len(rows)} usable names; expected {count}")
    return rows


def install_generic_naming_routes(app, app_module):
    if "api_generic_names" in app.view_functions:
        return

    @app.post("/api/generic-names")
    @app_module.limiter.limit(app_module.AI_RATE_LIMIT)
    def api_generic_names():
        data = app_module.json_object()
        if data is None:
            return app_module.jsonify({"error": "JSON body must be an object"}), 400
        brief = " ".join(str(data.get("brief") or "").split())
        if len(brief) < 3:
            return app_module.jsonify({"error": "Brief must contain at least 3 characters"}), 400
        if len(brief) > 1000:
            return app_module.jsonify({"error": "Brief must contain at most 1000 characters"}), 400
        try:
            count = max(1, min(20, int(data.get("count", 20))))
        except (TypeError, ValueError):
            count = 20
        try:
            generation_context = app_module.clean_generation_context(data.get("generation_context"))
        except ValueError as error:
            return app_module.jsonify({"error": str(error)}), 400
        preferences = app_module.clean_preferences(data.get("preferences"))

        if not app_module.AI_REQUEST_SLOTS.acquire(blocking=False):
            return app_module.jsonify({
                "error": "AI is busy. Please try again in a few seconds.",
                "retry_after": 5,
            }), 503, {"Retry-After": "5"}
        try:
            rows = generate_generic_names(brief, count, preferences, generation_context)
            return app_module.jsonify(rows)
        except Exception as error:
            app.logger.warning("Generic naming failed: %s", type(error).__name__)
            return app_module.jsonify({
                "error": "Temporary naming error. Please try again.",
                "error_type": type(error).__name__,
            }), 503
        finally:
            app_module.AI_REQUEST_SLOTS.release()


__all__ = [
    "GENERIC_FAMILIES",
    "generate_generic_names",
    "install_generic_naming_routes",
]
