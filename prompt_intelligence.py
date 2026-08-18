import json
import os
import re
from urllib.parse import urlsplit

from availability import RESOURCE_KEYS, normalize_resources


INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "task": {"type": "string", "enum": [
            "new_brand_naming",
            "existing_identity_search",
            "existing_identity_adaptation",
        ]},
        "search_mode": {"type": "string", "enum": [
            "new_brand",
            "existing_brand_fixed",
            "existing_brand_adaptable",
        ]},
        "entity_type": {"type": "string"},
        "brand_name": {"type": "string"},
        "brand_lock": {"type": "string", "enum": ["new", "fixed", "adaptable"]},
        "website_urls": {"type": "array", "items": {"type": "string"}},
        "owned_resources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "resource": {"type": "string", "enum": list(RESOURCE_KEYS)},
                    "value": {"type": "string"},
                },
                "required": ["resource", "value"],
                "additionalProperties": False,
            },
        },
        "inferred_requested_resources": {
            "type": "array",
            "items": {"type": "string", "enum": list(RESOURCE_KEYS)},
        },
        "semantic_brief": {"type": "string"},
        "core_concepts": {"type": "array", "items": {"type": "string"}},
        "secondary_concepts": {"type": "array", "items": {"type": "string"}},
        "metaphor_directions": {"type": "array", "items": {"type": "string"}},
        "naming_roots": {
            "type": "array",
            "items": {"type": "string", "pattern": "^[a-z]{3,20}$"},
        },
        "brand_traits": {"type": "array", "items": {"type": "string"}},
        "audience": {"type": "array", "items": {"type": "string"}},
        "market": {"type": "array", "items": {"type": "string"}},
        "languages": {"type": "array", "items": {"type": "string"}},
        "avoid_words": {"type": "array", "items": {"type": "string"}},
        "avoid_suffixes": {"type": "array", "items": {"type": "string"}},
        "avoid_styles": {"type": "array", "items": {"type": "string"}},
        "literal_non_seed_words": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "clarification_needed": {"type": "boolean"},
        "clarification_question": {"type": "string"},
    },
    "required": [
        "task", "search_mode", "entity_type", "brand_name", "brand_lock",
        "website_urls", "owned_resources", "inferred_requested_resources",
        "semantic_brief", "core_concepts", "secondary_concepts",
        "metaphor_directions", "naming_roots", "brand_traits", "audience",
        "market", "languages", "avoid_words", "avoid_suffixes", "avoid_styles",
        "literal_non_seed_words", "confidence", "clarification_needed",
        "clarification_question",
    ],
    "additionalProperties": False,
}


INTENT_SYSTEM_PROMPT = """You are the interpretation layer in a naming and digital-identity system.
Your job is to understand what the human means BEFORE any name generator sees the text.

Rules:
1. A prompt can be one word, a short phrase, a long description, or contain URLs. All are valid.
2. For short category prompts such as 'автосервіс', 'dentist', or 'колеса до машин', infer the likely business/entity and EXPAND it into useful semantic territory. Do not merely transliterate or repeat the literal phrase.
3. For long prompts, COMPRESS and STRUCTURE the meaning. Separate user instructions and prose glue from naming semantics.
4. Words equivalent to 'I', 'want', 'need', 'find', 'name', 'for', 'all', 'please', 'business', and similar instruction glue must not become naming roots unless they are explicitly part of the desired brand.
5. naming_roots must be short lowercase ASCII English/Latin naming-ready roots representing the actual concept, not prose tokens.
6. Detect whether this is a new brand, an existing locked brand, or an existing adaptable brand. If the user explicitly says the name cannot change, use existing_brand_fixed. If an existing name may change slightly, use existing_brand_adaptable.
7. Detect owned digital resources and resources explicitly requested in prose. The selected checkboxes supplied separately are the actual resources that will be checked; do not override them.
8. Extract URLs mentioned in the prompt, but do not claim to have visited them.
9. Respect explicit negative constraints such as forbidden words, suffixes, or styles.
10. Ask for clarification only when ambiguity would materially change the search. A bare category word should usually NOT require clarification. A bare brand-like proper name such as 'Velo' may require one short question if it is unclear whether it is an existing brand or merely inspiration.
11. semantic_brief must describe the entity, naming goal, positioning, and semantic territory in concise Ukrainian. Explanations and clarification questions must be Ukrainian.
12. Never claim availability, ownership, trademark status, or facts not stated by the user.
13. Generate broad semantic and metaphor directions; do not solve the naming task by outputting candidate brand names.
"""


def _bounded_text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _bounded_list(value, limit=16, item_limit=80):
    if not isinstance(value, list):
        return []
    output = []
    seen = set()
    for item in value[:limit]:
        text = _bounded_text(item, item_limit)
        key = text.lower()
        if text and key not in seen:
            output.append(text)
            seen.add(key)
    return output


def _extract_urls(prompt):
    candidates = re.findall(r"https?://[^\s<>'\"]+", str(prompt or ""), flags=re.I)
    output = []
    for raw in candidates[:5]:
        value = raw.rstrip(".,;:!?)]}")
        try:
            parsed = urlsplit(value)
        except ValueError:
            continue
        if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
            output.append(value[:2048])
    return output


def _clean_roots(value):
    roots = []
    seen = set()
    for item in value if isinstance(value, list) else []:
        root = re.sub(r"[^a-z]", "", str(item).lower())[:20]
        if 3 <= len(root) <= 20 and root not in seen:
            roots.append(root)
            seen.add(root)
        if len(roots) >= 20:
            break
    return roots


def clean_intelligence(value, prompt="", selected_resources=None):
    if not isinstance(value, dict):
        raise ValueError("Prompt interpreter returned an invalid object")

    mode = str(value.get("search_mode", "new_brand"))
    if mode not in {"new_brand", "existing_brand_fixed", "existing_brand_adaptable"}:
        mode = "new_brand"
    lock = {
        "new_brand": "new",
        "existing_brand_fixed": "fixed",
        "existing_brand_adaptable": "adaptable",
    }[mode]
    brand_name = _bounded_text(value.get("brand_name"), 80)
    if mode == "new_brand":
        brand_name = ""
    elif len(brand_name) < 2:
        mode = "new_brand"
        lock = "new"
        brand_name = ""

    inferred = []
    for resource in value.get("inferred_requested_resources", []):
        key = str(resource).lower()
        if key in RESOURCE_KEYS and key not in inferred:
            inferred.append(key)
    selected = list(normalize_resources(selected_resources)) if selected_resources is not None else []

    owned = []
    for row in value.get("owned_resources", []) if isinstance(value.get("owned_resources"), list) else []:
        if not isinstance(row, dict):
            continue
        resource = str(row.get("resource", "")).lower()
        item_value = _bounded_text(row.get("value"), 120)
        if resource in RESOURCE_KEYS and item_value:
            owned.append({"resource": resource, "value": item_value})
        if len(owned) >= 12:
            break

    urls = []
    for url in _extract_urls(prompt) + _bounded_list(value.get("website_urls"), 5, 2048):
        if url not in urls:
            urls.append(url)

    confidence = str(value.get("confidence", "medium"))
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    clarification_needed = bool(value.get("clarification_needed", False))
    clarification_question = _bounded_text(value.get("clarification_question"), 240)
    if not clarification_needed:
        clarification_question = ""

    return {
        "task": str(value.get("task", "new_brand_naming")),
        "search_mode": mode,
        "entity_type": _bounded_text(value.get("entity_type"), 120),
        "brand_name": brand_name,
        "brand_lock": lock,
        "website_urls": urls[:5],
        "owned_resources": owned,
        "inferred_requested_resources": inferred,
        "selected_resources": selected,
        "semantic_brief": _bounded_text(value.get("semantic_brief"), 1000),
        "core_concepts": _bounded_list(value.get("core_concepts"), 16),
        "secondary_concepts": _bounded_list(value.get("secondary_concepts"), 16),
        "metaphor_directions": _bounded_list(value.get("metaphor_directions"), 12),
        "naming_roots": _clean_roots(value.get("naming_roots")),
        "brand_traits": _bounded_list(value.get("brand_traits"), 12),
        "audience": _bounded_list(value.get("audience"), 10),
        "market": _bounded_list(value.get("market"), 10),
        "languages": _bounded_list(value.get("languages"), 10),
        "avoid_words": _bounded_list(value.get("avoid_words"), 16),
        "avoid_suffixes": _bounded_list(value.get("avoid_suffixes"), 12, 30),
        "avoid_styles": _bounded_list(value.get("avoid_styles"), 12),
        "literal_non_seed_words": _bounded_list(value.get("literal_non_seed_words"), 30, 40),
        "confidence": confidence,
        "clarification_needed": clarification_needed,
        "clarification_question": clarification_question,
    }


def interpret_prompt(prompt, selected_resources=None, feedback=None):
    safe_prompt = _bounded_text(prompt, 2000)
    if len(safe_prompt) < 2:
        raise ValueError("Prompt must contain at least 2 characters")
    resources = list(normalize_resources(selected_resources)) if selected_resources is not None else []
    safe_feedback = feedback if isinstance(feedback, dict) else {}

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    client = OpenAI()
    response = client.responses.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
        instructions=INTENT_SYSTEM_PROMPT,
        input=(
            "Interpret this naming/search request. Selected resource checkboxes are an explicit override "
            "for what the product will actually check.\n\n"
            f"USER_PROMPT:\n{safe_prompt}\n\n"
            f"SELECTED_RESOURCES:\n{json.dumps(resources, ensure_ascii=False)}\n\n"
            f"EXPLICIT_SESSION_FEEDBACK:\n{json.dumps(safe_feedback, ensure_ascii=False)[:4000]}"
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "prompt_intelligence",
                "strict": True,
                "schema": INTENT_SCHEMA,
            }
        },
        store=False,
    )
    return clean_intelligence(json.loads(response.output_text), safe_prompt, resources)
