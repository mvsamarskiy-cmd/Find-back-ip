"""Standalone naming workflow for non-brand tasks.

This endpoint intentionally performs no domain/social/company/trademark lookup.
It is for users who simply want a name, nickname, project title, bot name, game
handle idea, character name, or another naming concept.
"""
from __future__ import annotations

import json
import os
import re


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


def _clean_rows(rows, count, excluded):
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
        if len(output) >= count:
            break
    return output


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
    rows = _clean_rows(payload.get("names"), count, excluded)
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


__all__ = ["GENERIC_FAMILIES", "generate_generic_names", "install_generic_naming_routes"]
