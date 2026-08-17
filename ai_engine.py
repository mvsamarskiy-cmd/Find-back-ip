import json
import os
import re
import unicodedata
from difflib import SequenceMatcher


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


SYSTEM_PROMPT = """You are a rigorous international naming strategist.
Generate names for the exact entity, audience, market, language, and purpose in
the user's brief. Prefer distinctive, memorable, pronounceable names over random
letter strings or generic descriptions. Treat project feedback as evidence of
the user's taste: learn patterns from liked examples, avoid patterns from disliked
examples, but do not merely mutate or copy them. Never claim trademark, domain,
company, website, or handle availability. Explain every candidate in Ukrainian
and report possible negative meanings and pronunciation concerns honestly.
Candidate names must contain only ASCII Latin letters A-Z: no spaces, hyphens,
apostrophes, digits, diacritics, or Cyrillic. Never use a candidate containing any
forbidden root or ending listed in the generation plan."""


GENERATION_FAMILIES = (
    "direct semantic compounds grounded in the brief",
    "evocative metaphors with a defensible connection to the brief",
    "root blends or portmanteaus that remain easy to spell",
    "invented phonetic names with natural syllables",
    "short abstract names that can acquire brand meaning",
)


SCHEMA = {
    "type": "object",
    "properties": {
        "names": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "reason": {"type": "string"},
                    "pronunciation": {"type": "string"},
                    "language_risks": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "reason", "pronunciation", "language_risks"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["names"],
    "additionalProperties": False,
}


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


def _too_similar(left, right):
    a, b = _normalized_name(left), _normalized_name(right)
    if not a or not b:
        return True
    if a == b:
        return True
    if abs(len(a) - len(b)) <= 1 and SequenceMatcher(None, a, b).ratio() >= 0.84:
        return True
    signature_a, signature_b = _phonetic_signature(a), _phonetic_signature(b)
    return (
        len(a) >= 5
        and len(b) >= 5
        and signature_a == signature_b
        and abs(len(a) - len(b)) <= 2
    )


def _is_allowed_name(value):
    """Enforce the canonical candidate alphabet and blacklist."""
    name = str(value).strip()
    if not re.fullmatch(r"[A-Za-z]{3,30}", name):
        return False
    normalized = name.lower()
    if any(root in normalized for root in BANNED_ROOTS):
        return False
    if any(normalized.endswith(suffix) for suffix in BANNED_SUFFIXES):
        return False
    return True


def select_diverse_names(candidates, count):
    """Keep valid candidates while removing exact and near duplicates."""
    selected = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        name = str(candidate.get("name", "")).strip()
        if not _is_allowed_name(name):
            continue
        if any(_too_similar(name, row["name"]) for row in selected):
            continue
        clean = dict(candidate)
        clean["name"] = name
        selected.append(clean)
        if len(selected) >= count:
            break
    return selected


def _generation_plan(count):
    pool_size = min(40, max(count + 8, count * 2))
    families = "\n".join(f"- {family}" for family in GENERATION_FAMILIES)
    return pool_size, (
        "Diversify the pool evenly across these naming families:\n"
        f"{families}\n"
        "Avoid repeated suffixes, one-letter variants, and names with the same "
        "consonant skeleton. Do not repeat a candidate in another spelling.\n"
        f"Forbidden roots anywhere in a name: {', '.join(sorted(BANNED_ROOTS))}.\n"
        f"Forbidden endings: {', '.join(sorted(BANNED_SUFFIXES))}."
    )


def generate_ai_names(brief, count=10, preferences=None):
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    client = OpenAI()
    pool_size, plan = _generation_plan(count)
    response = client.responses.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
        instructions=SYSTEM_PROMPT,
        input=(
            f"Generate exactly {pool_size} distinct candidates for a final shortlist of {count}.\n"
            f"Project brief: {brief}\n"
            f"Project-specific feedback: {_preference_context(preferences)}\n"
            f"Generation plan:\n{plan}"
        ),
        text={"format": {"type": "json_schema", "name": "brand_names", "strict": True, "schema": SCHEMA}},
        store=False,
    )
    data = json.loads(response.output_text)
    selected = select_diverse_names(data["names"], count)
    if len(selected) < count:
        raise ValueError(
            f"AI returned only {len(selected)} valid candidates; expected {count}"
        )
    return selected


def trademark_links(name):
    query = name.strip()
    return {
        "notice": "Manual legal search required; these links do not prove availability.",
        "euipo": f"https://euipo.europa.eu/eSearch/#basic/1+1+1+1/{query}",
        "wipo": "https://branddb.wipo.int/",
        "uprp": "https://ewyszukiwarka.pue.uprp.gov.pl/search/simple-search",
    }
