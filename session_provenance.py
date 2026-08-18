"""Bounded persistence bridge for candidate provenance metadata.

The browser/session sanitizer intentionally whitelists candidate fields. Generation
and verification provenance were added after that whitelist, so this module wraps
the sanitizer at bootstrap and re-attaches only a fixed non-secret subset. Large
or arbitrary provider payloads are never copied through this bridge.
"""

from __future__ import annotations

import json
from functools import wraps


GENERATION_KEYS = {
    "generator_version": 64,
    "naming_prompt_version": 64,
    "prompt_intelligence_version": 64,
    "model": 96,
    "candidate_source": 64,
    "candidate_schema_version": 64,
}
VERIFICATION_KEYS = {
    "verification_engine_version": 64,
    "evidence_fusion_version": 64,
    "candidate_schema_version": 64,
}


def _clean_text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _clean_map(value, allowed):
    if not isinstance(value, dict):
        return None
    result = {}
    for key, limit in allowed.items():
        clean = _clean_text(value.get(key), limit)
        if clean:
            result[key] = clean
    return result or None


def clean_generation_provenance(value):
    return _clean_map(value, GENERATION_KEYS)


def clean_verification_provenance(value):
    return _clean_map(value, VERIFICATION_KEYS)


def install_session_provenance(session_api_module):
    """Wrap ``session_api._clean_candidate`` once and preserve safe provenance.

    The original sanitizer remains authoritative for all existing candidate data.
    This wrapper only re-attaches two compact version maps from the original row,
    then re-applies the candidate byte budget before persistence.
    """
    current = session_api_module._clean_candidate
    if getattr(current, "_namemachine_provenance_persistence", False):
        return current
    original = current

    @wraps(original)
    def wrapped(row, app_module):
        clean = original(row, app_module)
        if clean is None or not isinstance(row, dict):
            return clean

        generation = clean_generation_provenance(row.get("generation_provenance"))
        verification = clean_verification_provenance(row.get("verification_provenance"))
        if generation:
            clean["generation_provenance"] = generation
        if verification:
            clean["verification_provenance"] = verification

        encoded = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > session_api_module.MAX_CANDIDATE_BYTES:
            raise ValueError(f"Candidate {clean.get('name', '')} payload is too large")
        return clean

    wrapped._namemachine_provenance_persistence = True
    wrapped._namemachine_original = original
    session_api_module._clean_candidate = wrapped
    return wrapped


__all__ = [
    "GENERATION_KEYS",
    "VERIFICATION_KEYS",
    "clean_generation_provenance",
    "clean_verification_provenance",
    "install_session_provenance",
]
