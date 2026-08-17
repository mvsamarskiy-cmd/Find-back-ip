import json
import os


SYSTEM_PROMPT = """You are a rigorous international naming strategist.
Generate names for the exact entity, audience, market, language, and purpose in
the user's brief. Prefer distinctive, memorable, pronounceable names over random
letter strings or generic descriptions. Treat project feedback as evidence of
the user's taste: learn patterns from liked examples, avoid patterns from disliked
examples, but do not merely mutate or copy them. Never claim trademark, domain,
company, website, or handle availability. Explain every candidate in Ukrainian
and report possible negative meanings and pronunciation concerns honestly."""


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


def generate_ai_names(brief, count=10, preferences=None):
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    client = OpenAI()
    response = client.responses.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
        instructions=SYSTEM_PROMPT,
        input=(
            f"Generate exactly {count} distinct candidates.\n"
            f"Project brief: {brief}\n"
            f"Project-specific feedback: {_preference_context(preferences)}"
        ),
        text={"format": {"type": "json_schema", "name": "brand_names", "strict": True, "schema": SCHEMA}},
        store=False,
    )
    data = json.loads(response.output_text)
    return data["names"][:count]


def trademark_links(name):
    query = name.strip()
    return {
        "notice": "Manual legal search required; these links do not prove availability.",
        "euipo": f"https://euipo.europa.eu/eSearch/#basic/1+1+1+1/{query}",
        "wipo": "https://branddb.wipo.int/",
        "uprp": "https://ewyszukiwarka.pue.uprp.gov.pl/search/simple-search",
    }
