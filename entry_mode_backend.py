"""Product-entry mode authority for NameMachine.

Prompt Intelligence may infer a search mode from prose, but an explicit UI mode
selected by the human is stronger evidence. We carry that authority through the
existing bounded guidance field with a short internal marker, avoiding a live DB
schema migration while keeping old clients backward compatible.
"""
from __future__ import annotations

import re


MARKER_RE = re.compile(r"\[\[nm-mode-lock:(new_brand|existing_brand_fixed|existing_brand_adaptable)\]\]", re.I)
_LOCK_MAP = {
    "new_brand": ("new_brand_naming", "new"),
    "existing_brand_fixed": ("existing_identity_search", "fixed"),
    "existing_brand_adaptable": ("existing_identity_adaptation", "adaptable"),
}
_INSTALLED = False


def mode_lock_marker(mode):
    if mode not in _LOCK_MAP:
        raise ValueError("Unsupported entry-mode lock")
    return f"[[nm-mode-lock:{mode}]]"


def strip_mode_lock(value):
    return " ".join(MARKER_RE.sub("", str(value or "")).split())


def install_entry_mode_intelligence(app_module):
    """Wrap app.apply_prompt_intelligence so explicit product mode wins.

    The wrapper never changes naming roots, semantic interpretation, or verifier
    evidence. It only restores the user-selected search mode after the AI
    interpreter has structured the prose.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    base = app_module.apply_prompt_intelligence

    def apply_with_entry_mode_lock(brief, resources, search_context):
        requested = dict(search_context or {})
        guidance = str(requested.get("guidance") or "")
        match = MARKER_RE.search(guidance)
        clean_guidance = strip_mode_lock(guidance)
        requested["guidance"] = clean_guidance

        compiled_brief, compiled_context, intelligence = base(
            brief,
            resources,
            requested,
        )
        compiled_context = dict(compiled_context or {})
        intelligence = dict(intelligence or {})

        if match:
            mode = match.group(1).lower()
            task, lock = _LOCK_MAP[mode]
            brand_name = " ".join(str(requested.get("brand_name") or "").split())[:80]
            if mode != "new_brand" and len(brand_name) < 2:
                raise ValueError("Existing-brand mode requires a brand name")
            compiled_context["mode"] = mode
            compiled_context["brand_name"] = "" if mode == "new_brand" else brand_name
            compiled_context["guidance"] = strip_mode_lock(compiled_context.get("guidance"))[:500]
            intelligence["search_mode"] = mode
            intelligence["brand_name"] = compiled_context["brand_name"]
            intelligence["brand_lock"] = lock
            intelligence["task"] = task

        return compiled_brief, compiled_context, intelligence

    app_module.apply_prompt_intelligence = apply_with_entry_mode_lock
    _INSTALLED = True


__all__ = [
    "install_entry_mode_intelligence",
    "mode_lock_marker",
    "strip_mode_lock",
]
