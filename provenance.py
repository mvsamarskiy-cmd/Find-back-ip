"""Stable, non-secret provenance labels for reproducible NameMachine results."""

from __future__ import annotations

from functools import wraps
import importlib
import os
import sys


GENERATOR_VERSION = "namemachine-generator-v3"
NAMING_PROMPT_VERSION = "naming-prompt-v2"
PROMPT_INTELLIGENCE_VERSION = "prompt-intelligence-v1"
VERIFICATION_ENGINE_VERSION = "verification-engine-v2"
EVIDENCE_FUSION_VERSION = "evidence-fusion-v2"
CANDIDATE_SCHEMA_VERSION = "candidate-result-v2"


def generation_provenance(candidate_source=None):
    source = str(candidate_source or "openai").strip()[:64] or "openai"
    return {
        "generator_version": GENERATOR_VERSION,
        "naming_prompt_version": NAMING_PROMPT_VERSION,
        "prompt_intelligence_version": PROMPT_INTELLIGENCE_VERSION,
        "model": str(os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"))[:96],
        "candidate_source": source,
        "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
    }


def verification_provenance():
    return {
        "verification_engine_version": VERIFICATION_ENGINE_VERSION,
        "evidence_fusion_version": EVIDENCE_FUSION_VERSION,
        "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
    }


def annotate_generated_candidates(rows):
    """Attach immutable generation labels without mutating generator-owned rows."""
    if rows is None:
        return rows
    output = []
    for raw in rows:
        if not isinstance(raw, dict):
            output.append(raw)
            continue
        row = dict(raw)
        row["generation_provenance"] = generation_provenance(
            row.get("candidate_source")
        )
        output.append(row)
    return output


def install_generation_provenance(ai_module=None, app_module=None):
    """Wrap the generator once and update already-imported app globals if needed.

    ``app.py`` imports ``generate_ai_names`` by value. Production bootstrap and the
    background worker import Verification v2 after ``app`` has loaded, so patching
    only ``ai_engine.generate_ai_names`` would leave the app's existing reference
    stale. This installer safely points both references at the same idempotent
    wrapper while preserving the original function signature/call shape.
    """
    if ai_module is None:
        ai_module = importlib.import_module("ai_engine")
    current = getattr(ai_module, "generate_ai_names")
    if getattr(current, "_namemachine_provenance_wrapped", False):
        wrapped = current
    else:
        original = current

        @wraps(original)
        def wrapped(*args, **kwargs):
            return annotate_generated_candidates(original(*args, **kwargs))

        wrapped._namemachine_provenance_wrapped = True
        wrapped._namemachine_original = original
        ai_module.generate_ai_names = wrapped

    target_app = app_module if app_module is not None else sys.modules.get("app")
    if target_app is not None and hasattr(target_app, "generate_ai_names"):
        target_app.generate_ai_names = wrapped
    return wrapped


__all__ = [
    "CANDIDATE_SCHEMA_VERSION",
    "EVIDENCE_FUSION_VERSION",
    "GENERATOR_VERSION",
    "NAMING_PROMPT_VERSION",
    "PROMPT_INTELLIGENCE_VERSION",
    "VERIFICATION_ENGINE_VERSION",
    "annotate_generated_candidates",
    "generation_provenance",
    "install_generation_provenance",
    "verification_provenance",
]
