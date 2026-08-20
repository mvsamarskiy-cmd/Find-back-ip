"""Runtime integration for the local creative lexicon.

The existing naming model remains the semantic reasoner.  This overlay gives it a
small retrieved palette and gives the deterministic local expander the same roots,
without a second AI request or a remote dictionary lookup.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from creative_lexicon import creative_palette, creative_palette_prompt


PRIVATE_PALETTE_KEY = "_namemachine_creative_palette"


def _ascii_root(value: Any) -> str:
    return re.sub(r"[^a-z]", "", str(value or "").lower())[:30]


def _guidance_forbidden(guidance="", brand_dna=None) -> set[str]:
    """Extract explicit word exclusions already compiled by Prompt Intelligence."""
    output = set()
    text = " ".join(str(guidance or "").split())
    lowered = text.lower()
    markers = (
        "не використовувати слова:",
        "avoid words:",
        "forbidden words:",
        "do not use words:",
    )
    for marker in markers:
        start = lowered.find(marker)
        if start < 0:
            continue
        fragment = text[start + len(marker):].split("|", 1)[0]
        for raw in fragment.split(",")[:20]:
            root = _ascii_root(raw)
            if root:
                output.add(root)
    if isinstance(brand_dna, dict):
        for raw in brand_dna.get("avoid", []) if isinstance(brand_dna.get("avoid"), list) else []:
            root = _ascii_root(raw)
            if root:
                output.add(root)
    return output


def _with_private_palette(brand_dna, palette):
    value = deepcopy(brand_dna) if isinstance(brand_dna, dict) else {}
    value[PRIVATE_PALETTE_KEY] = deepcopy(palette)
    return value


def _local_brand_dna(brand_dna):
    """Expose a bounded subset of retrieved roots only to the cheap local expander."""
    value = deepcopy(brand_dna) if isinstance(brand_dna, dict) else {}
    palette = value.pop(PRIVATE_PALETTE_KEY, None)
    if not isinstance(palette, dict) or not palette.get("matched_clusters"):
        return value

    existing_keywords = list(value.get("keywords") or []) if isinstance(value.get("keywords"), list) else []
    existing_themes = list(value.get("themes") or []) if isinstance(value.get("themes"), list) else []
    existing_directions = list(value.get("naming_directions") or []) if isinstance(value.get("naming_directions"), list) else []

    # Preserve user/Brand-DNA material as the majority of each bounded field.
    value["keywords"] = existing_keywords[:8] + list(palette.get("local_roots") or [])[:8]
    value["themes"] = existing_themes[:8] + list(palette.get("matched_clusters") or [])[:4]
    bridge = list(palette.get("bridge_clusters") or [])[:4]
    if bridge:
        existing_directions = existing_directions[:8] + ["semantic bridge " + " ".join(bridge)]
    value["naming_directions"] = existing_directions
    return value


def install_creative_generation(ai_module, app_module=None) -> None:
    """Install a concurrency-safe, idempotent lexicon overlay."""
    base_generate = ai_module.generate_ai_names
    if getattr(base_generate, "_creative_lexicon_wrapper", False):
        if app_module is not None:
            app_module.generate_ai_names = base_generate
        return

    base_brand_context = ai_module.brand_dna_context
    base_expand = ai_module.expand_local_families

    def lexicon_brand_context(value):
        palette = value.get(PRIVATE_PALETTE_KEY) if isinstance(value, dict) else None
        public_value = deepcopy(value) if isinstance(value, dict) else value
        if isinstance(public_value, dict):
            public_value.pop(PRIVATE_PALETTE_KEY, None)
        base = base_brand_context(public_value)
        if not isinstance(palette, dict) or not palette.get("matched_clusters"):
            return base
        return base + "\nInternal creative semantic palette: " + creative_palette_prompt(palette)

    def lexicon_expand(brief="", brand_dna=None, limit=180):
        palette = brand_dna.get(PRIVATE_PALETTE_KEY) if isinstance(brand_dna, dict) else None
        rows = base_expand(brief, _local_brand_dna(brand_dna), limit=limit)
        if not isinstance(palette, dict) or not palette.get("matched_clusters"):
            return rows
        clusters = list(palette.get("matched_clusters") or [])[:4]
        bridges = list(palette.get("bridge_clusters") or [])[:4]
        enriched = []
        for row in rows:
            clean = dict(row)
            clean["creative_lexicon_version"] = "creative-lexicon-v1"
            clean["creative_lexicon_clusters"] = clusters
            clean["creative_lexicon_bridges"] = bridges
            clean["creative_lexicon_used"] = True
            enriched.append(clean)
        return enriched

    def generate(
        brief,
        count=10,
        preferences=None,
        brand_dna=None,
        search_context=None,
        generation_context=None,
    ):
        context = ai_module.clean_search_context(search_context)
        adaptive = ai_module.clean_generation_context(generation_context)
        forbidden = set(getattr(ai_module, "BANNED_ROOTS", ()))
        forbidden.update(getattr(ai_module, "BANNED_SUFFIXES", ()))
        forbidden.update(_guidance_forbidden(context.get("guidance"), brand_dna))
        palette = creative_palette(
            brief,
            brand_dna,
            context.get("guidance", ""),
            batch_number=adaptive.get("batch_number", 1),
            forbidden=forbidden,
        )
        enriched_dna = _with_private_palette(brand_dna, palette)
        rows = base_generate(
            brief,
            count=count,
            preferences=preferences,
            brand_dna=enriched_dna,
            search_context=context,
            generation_context=adaptive,
        )
        if not palette.get("matched_clusters"):
            return rows
        clusters = list(palette.get("matched_clusters") or [])[:4]
        bridges = list(palette.get("bridge_clusters") or [])[:4]
        output = []
        for row in rows:
            clean = dict(row)
            clean["creative_lexicon_version"] = "creative-lexicon-v1"
            clean["creative_lexicon_clusters"] = clusters
            clean["creative_lexicon_bridges"] = bridges
            clean["creative_lexicon_used"] = True
            output.append(clean)
        return output

    lexicon_brand_context._creative_lexicon_wrapper = True
    lexicon_expand._creative_lexicon_wrapper = True
    generate._creative_lexicon_wrapper = True
    ai_module.brand_dna_context = lexicon_brand_context
    ai_module.expand_local_families = lexicon_expand
    ai_module.generate_ai_names = generate
    if app_module is not None:
        app_module.generate_ai_names = generate


def creative_generation_diagnostics() -> dict[str, Any]:
    return {
        "enabled": True,
        "extra_model_calls_per_batch": 0,
        "remote_dictionary_calls": 0,
        "palette_is_bounded": True,
        "user_constraints_override_palette": True,
        "local_expander_uses_same_palette": True,
        "batch_semantic_bridge_rotation": True,
    }


__all__ = [
    "PRIVATE_PALETTE_KEY",
    "creative_generation_diagnostics",
    "install_creative_generation",
]
