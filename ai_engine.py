import json
import math
import os
import re
import unicodedata
from difflib import SequenceMatcher

from brand_dna import brand_dna_context
from candidate_funnel import rank_candidate_pool
from trademark_risk import trademark_search_plan


BANNED_ROOTS = {
    "idea", "product", "make", "maker", "creat", "build", "factory", "forge",
    "foundry", "lab", "studio", "shop", "store", "market", "communit", "crowd",
    "vote", "preorder", "drop", "pin", "merch", "object", "reality", "real",
    "ai", "tech",
}
BANNED_SUFFIXES = {
    "ora", "ova", "ira", "iva", "eya", "aya", "io", "ly", "ify", "verse",
    "works", "base", "hub", "flow", "labs",
}

SEARCH_MODES = (
    "new_brand",
    "existing_brand_fixed",
    "existing_brand_adaptable",
)
DEFAULT_SEARCH_CONTEXT = {
    "mode": "new_brand",
    "brand_name": "",
    "guidance": "",
}
DEFAULT_GENERATION_CONTEXT = {
    "batch_number": 1,
    "exclude_names": [],
    "conflict_names": [],
    "successful_names": [],
}

GENERATION_FAMILIES = {
    "semantic_compound": "direct semantic compounds grounded in the brief",
    "evocative_metaphor": "evocative metaphors with a defensible connection to the brief",
    "root_blend": "root blends or portmanteaus that remain easy to spell",
    "invented_phonetic": "invented phonetic names with natural syllables",
    "abstract": "short abstract names that can acquire brand meaning",
}
GENERATION_FAMILY_KEYS = tuple(GENERATION_FAMILIES)


SYSTEM_PROMPT = """You are a rigorous international naming and digital-identity strategist.
Generate candidates for the exact entity, audience, market, language, purpose,
search task, and structured Brand DNA supplied by the user. Prefer distinctive,
memorable, pronounceable candidates over random letter strings or generic
mutations. Treat explicit user prohibitions and requirements as hard constraints.
Treat project likes, dislikes, and reason weights as softer evidence of taste:
learn patterns from them, but do not merely mutate or copy previous candidates.
When prior batches are supplied, never recycle excluded names or create trivial
one-letter/one-suffix mutations of conflict names. If conflicts dominate a prior
batch, deliberately move into different semantic roots, metaphors, phonetic
structures, and naming families rather than staying in the saturated neighborhood.
Distribute candidates across the requested naming families instead of producing a
suffix monoculture. Label every candidate with its actual naming family. When an
existing brand is locked, generate resource-identifier stems tied to that brand
instead of inventing a replacement brand. Brand DNA is bounded context produced
from user-supplied sources, not an availability claim. Never claim trademark,
domain, company, website, or handle availability. Explain every candidate in
Ukrainian and report possible negative meanings and pronunciation concerns
honestly. Candidate names must contain only ASCII Latin letters A-Z: no spaces,
hyphens, apostrophes, digits, diacritics, or Cyrillic."""


SCHEMA = {
    "type": "object",
    "properties": {
        "names": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "family": {"type": "string", "enum": list(GENERATION_FAMILY_KEYS)},
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


def clean_search_context(value):
    """Validate and bound the user's search intent before it reaches the model."""
    if value is None:
        return dict(DEFAULT_SEARCH_CONTEXT)
    if not isinstance(value, dict):
        raise ValueError("search_context must be an object")

    mode = str(value.get("mode", "new_brand")).strip()
    if mode not in SEARCH_MODES:
        raise ValueError("Unknown search mode")

    brand_name = " ".join(str(value.get("brand_name", "")).split())
    guidance = " ".join(str(value.get("guidance", "")).split())
    if len(brand_name) > 80:
        raise ValueError("Brand name must contain at most 80 characters")
    if len(guidance) > 500:
        raise ValueError("Additional guidance must contain at most 500 characters")
    if mode != "new_brand" and len(brand_name) < 2:
        raise ValueError("Existing-brand modes require a brand name")
    if mode == "new_brand":
        brand_name = ""

    return {
        "mode": mode,
        "brand_name": brand_name,
        "guidance": guidance,
    }


def search_context_prompt(value):
    context = clean_search_context(value)
    mode = context["mode"]
    if mode == "existing_brand_fixed":
        task = (
            "The brand name is locked. Do not rename the brand. Generate candidate "
            "domain/handle stems that remain clearly tied to the existing brand. "
            "The candidate name is a digital identity variant, not a new brand."
        )
    elif mode == "existing_brand_adaptable":
        task = (
            "An existing brand already exists. Preserve it whenever practical and "
            "prefer close, recognizable identity variants; moderate adaptation is "
            "allowed only when it improves the requested digital identity."
        )
    else:
        task = (
            "Create a new brand identity. The candidate name may be genuinely new "
            "as long as it remains grounded in the brief and Brand DNA."
        )
    return json.dumps(
        {
            "mode": mode,
            "existing_brand": context["brand_name"] or None,
            "additional_guidance": context["guidance"] or None,
            "task_rule": task,
        },
        ensure_ascii=False,
    )


def _bounded_names(value, limit):
    if not isinstance(value, list):
        return []
    output = []
    seen = set()
    for raw in value[:limit]:
        name = "".join(ch for ch in str(raw).strip() if ch.isascii() and ch.isalpha())[:30]
        key = name.lower()
        if len(name) >= 3 and key not in seen:
            output.append(name)
            seen.add(key)
    return output


def clean_generation_context(value):
    """Bound cross-batch memory so repeated search stays predictable and cheap."""
    if value is None:
        return dict(DEFAULT_GENERATION_CONTEXT)
    if not isinstance(value, dict):
        raise ValueError("generation_context must be an object")
    try:
        batch_number = int(value.get("batch_number", 1))
    except (TypeError, ValueError):
        batch_number = 1
    return {
        "batch_number": max(1, min(5, batch_number)),
        "exclude_names": _bounded_names(value.get("exclude_names"), 100),
        "conflict_names": _bounded_names(value.get("conflict_names"), 40),
        "successful_names": _bounded_names(value.get("successful_names"), 20),
    }


def generation_context_prompt(value):
    context = clean_generation_context(value)
    rule = (
        "This is the first batch. Explore broadly across the available naming families."
        if context["batch_number"] == 1
        else (
            "This is an adaptive follow-up batch. Excluded names are forbidden. "
            "Conflict examples indicate saturated exact/nearby identity territory; "
            "do not make spelling mutations of them. Shift to different semantic "
            "roots and phonetic structures. Successful examples are directional "
            "evidence only; learn the quality pattern without cloning them."
        )
    )
    return json.dumps(
        {
            "batch_number": context["batch_number"],
            "excluded_names": context["exclude_names"],
            "conflict_examples": context["conflict_names"],
            "successful_examples": context["successful_names"],
            "adaptation_rule": rule,
        },
        ensure_ascii=False,
    )


def _preference_context(preferences):
    if not isinstance(preferences, dict):
        return "No project-specific feedback yet."

    def clean_examples(key):
        values = preferences.get(key, [])
        if not isinstance(values, list):
            return []
        return [str(value).strip()[:40] for value in values[:20] if str(value).strip()]

    liked = clean_examples("liked")
    disliked = clean_examples("disliked")
    reasons = preferences.get("reasons", {})
    if not isinstance(reasons, dict):
        reasons = {}
    safe_reasons = {
        str(key)[:30]: max(-20, min(20, int(value)))
        for key, value in list(reasons.items())[:20]
        if isinstance(value, (int, float))
    }
    return json.dumps(
        {"liked_examples": liked, "disliked_examples": disliked, "reason_weights": safe_reasons},
        ensure_ascii=False,
    )


def _normalized_name(value):
    ascii_value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", ascii_value.lower())


def _phonetic_signature(value):
    """Return a conservative signature for invented-name near-duplicates."""
    name = _normalized_name(value)
    if not name:
        return ""
    collapsed = re.sub(r"(.)\1+", r"\1", name)
    consonants = re.sub(r"[aeiouy]", "", collapsed[1:])
    return collapsed[0] + consonants


def _visual_signature(value):
    """Normalize a few common Latin-letter visual confusions conservatively."""
    name = _normalized_name(value)
    if not name:
        return ""
    name = name.replace("rn", "m").replace("vv", "w")
    return re.sub(r"(.)\1+", r"\1", name)


def _edit_distance(left, right, limit=2):
    """Small bounded Levenshtein distance used only for near-duplicate rejection."""
    a, b = _normalized_name(left), _normalized_name(right)
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        row_min = i
        for j, char_b in enumerate(b, 1):
            value = min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (char_a != char_b),
            )
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return limit + 1
        previous = current
    return previous[-1]


def _too_similar(left, right):
    a, b = _normalized_name(left), _normalized_name(right)
    if not a or not b:
        return True
    if a == b:
        return True
    if min(len(a), len(b)) >= 5 and _edit_distance(a, b, 1) <= 1:
        return True
    if abs(len(a) - len(b)) <= 1 and SequenceMatcher(None, a, b).ratio() >= 0.84:
        return True
    signature_a, signature_b = _phonetic_signature(a), _phonetic_signature(b)
    if (
        len(a) >= 5
        and len(b) >= 5
        and signature_a == signature_b
        and abs(len(a) - len(b)) <= 2
    ):
        return True
    visual_a, visual_b = _visual_signature(a), _visual_signature(b)
    return (
        min(len(a), len(b)) >= 5
        and visual_a == visual_b
        and abs(len(a) - len(b)) <= 2
    )


def _is_allowed_name(value, search_context=None):
    """Enforce the candidate alphabet and new-brand blacklist."""
    name = str(value).strip()
    if not re.fullmatch(r"[A-Za-z]{3,30}", name):
        return False
    context = clean_search_context(search_context)
    if context["mode"] != "new_brand":
        return True
    normalized = name.lower()
    if any(root in normalized for root in BANNED_ROOTS):
        return False
    if any(normalized.endswith(suffix) for suffix in BANNED_SUFFIXES):
        return False
    return True


def select_diverse_names(candidates, count, search_context=None, exclude_names=None):
    """Rank locally, then enforce cross-batch and naming-family diversity."""
    selected = []
    blocked = _bounded_names(exclude_names, 100)
    family_counts = {family: 0 for family in GENERATION_FAMILY_KEYS}
    family_cap = max(2, math.ceil(max(1, count) / 3))

    for candidate in rank_candidate_pool(candidates):
        name = str(candidate.get("name", "")).strip()
        family = str(candidate.get("family", "")).strip()
        if not _is_allowed_name(name, search_context):
            continue
        if any(_too_similar(name, old) for old in blocked):
            continue
        if any(_too_similar(name, row["name"]) for row in selected):
            continue
        if family in family_counts and family_counts[family] >= family_cap:
            continue
        clean = dict(candidate)
        clean["name"] = name
        if family in family_counts:
            clean["family"] = family
            family_counts[family] += 1
        selected.append(clean)
        if len(selected) >= count:
            break
    return selected


def _generation_plan(count, search_context=None, generation_context=None):
    context = clean_search_context(search_context)
    adaptive = clean_generation_context(generation_context)
    pool_size = min(40, max(count + 8, count * 2))
    families = "\n".join(
        f"- {key}: {description}" for key, description in GENERATION_FAMILIES.items()
    )
    if context["mode"] == "new_brand":
        rules = (
            "Diversify the pool across these naming families and label each candidate "
            "with the matching family key:\n"
            f"{families}\n"
            "Do not let one family dominate the pool. Avoid repeated suffixes, "
            "one-letter variants, visually confusable variants, and names with the "
            "same consonant skeleton. Do not repeat a candidate in another spelling.\n"
            f"Forbidden roots anywhere in a name: {', '.join(sorted(BANNED_ROOTS))}.\n"
            f"Forbidden endings: {', '.join(sorted(BANNED_SUFFIXES))}."
        )
    else:
        rules = (
            "Generate diverse digital-identity variants for the existing brand and "
            "still distribute them across the available naming-family labels below:\n"
            f"{families}\n"
            "Use meaningful prefixes, suffixes, compounds, or concise brand-linked "
            "forms instead of one-letter mutations. Do not apply the new-brand "
            "blacklist to words already present in an established brand. Avoid "
            "repeated suffixes, visual near-duplicates, and phonetic near-duplicates."
        )
    if adaptive["batch_number"] > 1:
        rules += (
            "\nAdaptive rule: this is a follow-up batch. Deliberately change lexical "
            "and phonetic neighborhoods from prior conflict examples; do not merely "
            "attach a new suffix to a failed root."
        )
    return pool_size, rules


def generate_ai_names(
    brief,
    count=10,
    preferences=None,
    brand_dna=None,
    search_context=None,
    generation_context=None,
):
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    context = clean_search_context(search_context)
    adaptive = clean_generation_context(generation_context)
    client = OpenAI()
    pool_size, plan = _generation_plan(count, context, adaptive)
    response = client.responses.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
        instructions=SYSTEM_PROMPT,
        input=(
            f"Generate exactly {pool_size} distinct candidates for a final shortlist of {count}.\n"
            f"Project brief: {brief}\n"
            f"Search task: {search_context_prompt(context)}\n"
            f"Structured Brand DNA: {brand_dna_context(brand_dna)}\n"
            f"Project-specific feedback: {_preference_context(preferences)}\n"
            f"Adaptive batch context: {generation_context_prompt(adaptive)}\n"
            f"Generation plan:\n{plan}"
        ),
        text={"format": {"type": "json_schema", "name": "brand_names", "strict": True, "schema": SCHEMA}},
        store=False,
    )
    data = json.loads(response.output_text)
    selected = select_diverse_names(
        data["names"],
        count,
        context,
        exclude_names=adaptive["exclude_names"],
    )
    if len(selected) < count:
        raise ValueError(
            f"AI returned only {len(selected)} valid candidates; expected {count}"
        )
    return selected


def trademark_links(name):
    """Backward-compatible name kept for API callers; now returns a risk plan."""
    return trademark_search_plan(name)
