"""Stable, non-secret provenance labels for reproducible NameMachine results."""

from __future__ import annotations

import os


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


__all__ = [
    "CANDIDATE_SCHEMA_VERSION",
    "EVIDENCE_FUSION_VERSION",
    "GENERATOR_VERSION",
    "NAMING_PROMPT_VERSION",
    "PROMPT_INTELLIGENCE_VERSION",
    "VERIFICATION_ENGINE_VERSION",
    "generation_provenance",
    "verification_provenance",
]
