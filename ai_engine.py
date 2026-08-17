import json
import os


SYSTEM_PROMPT = """You are a rigorous international brand-name generator.
Return short names that are easy to pronounce in English and are not tied to a
country, pins, or one product. They should fit a community that votes ideas into
limited physical products. Never claim trademark or handle availability. Flag
possible negative meanings and phonetic concerns honestly."""


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


def generate_ai_names(brief, count=10):
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    client = OpenAI()
    response = client.responses.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
        instructions=SYSTEM_PROMPT,
        input=f"Generate exactly {count} distinct candidates. Brand brief: {brief}",
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
