"""Evidence-aware eligibility compiler for Money / Material Opportunity Intelligence v2.2.

The engine extracts explicit requirements from observed source text and compares
only facts explicitly known from the user's current query/profile. Missing data
remains missing. `eligible_candidate` means all *observed* mandatory rules were
matched; it is never a legal eligibility determination or award guarantee.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


MONEY_ELIGIBILITY_VERSION = "money-eligibility-v2.2"


@dataclass(frozen=True)
class Rule:
    id: str
    field: str
    operator: str
    value: Any
    evidence: str
    confidence: float
    mandatory: bool = True


def _clean(value: object, limit: int = 50000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _context(text: str, start: int, end: int, radius: int = 100) -> str:
    return _clean(text[max(0, start-radius):min(len(text), end+radius)], 260)


def _num(raw: object) -> float | None:
    try:
        return float(str(raw).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _money_value(raw: object, suffix: object = None) -> int | None:
    value = _num(raw)
    if value is None:
        return None
    suffix = str(suffix or "").lower().rstrip(".")
    mult = 1_000 if suffix in {"k", "tys", "thousand", "тис"} else 1_000_000 if suffix in {"m", "mln", "million", "млн"} else 1
    return int(round(value * mult))


def _currency(raw: object) -> str | None:
    token = str(raw or "").strip().lower()
    return {"pln":"PLN", "zł":"PLN", "zl":"PLN", "eur":"EUR", "€":"EUR", "usd":"USD", "$":"USD"}.get(token)


def extract_eligibility_rules(text: object) -> list[dict]:
    """Extract explicit, machine-checkable eligibility rules with provenance."""
    raw = _clean(text)
    lower = raw.casefold()
    rules: list[Rule] = []

    def add(rule: Rule):
        key = (rule.id, rule.operator, str(rule.value))
        if not any((r.id, r.operator, str(r.value)) == key for r in rules):
            rules.append(rule)

    applicant_patterns = {
        "sme": (r"(?:only|eligible applicants? (?:are|include)|open to)\s+(?:micro,?\s*)?(?:small and medium(?:-sized)? enterprises|smes?)", r"(?:wyłącznie|dla)\s+(?:mikro,?\s*)?(?:małych i średnich przedsiębiorstw|mśp)", r"(?:лише|для)\s+(?:малих та середніх підприємств|мсп)"),
        "startup": (r"(?:only|open to|eligible applicants? include)\s+start-?ups?", r"(?:wyłącznie|dla)\s+start-?up(?:ów|y)?", r"(?:лише|для)\s+стартап(?:ів|и)?"),
        "company": (r"(?:only|open to)\s+(?:companies|businesses|enterprises)", r"(?:wyłącznie|dla)\s+(?:firm|przedsiębiorc)", r"(?:лише|для)\s+(?:компаній|підприємств|бізнесу)"),
        "ngo": (r"(?:only|open to)\s+(?:ngos?|non-?profits?|foundations?)", r"(?:wyłącznie|dla)\s+(?:ngo|fundacj|stowarzysze)", r"(?:лише|для)\s+(?:нго|фондів|організацій)"),
        "individual": (r"(?:only|open to)\s+(?:individuals?|natural persons?)", r"(?:wyłącznie|dla)\s+osób fizycznych", r"(?:лише|для)\s+фізичних осіб"),
    }
    for applicant, patterns in applicant_patterns.items():
        for pattern in patterns:
            for match in re.finditer(pattern, lower, flags=re.I):
                add(Rule(f"applicant:{applicant}", "applicant_type", "contains", applicant, _context(raw, match.start(), match.end()), 0.9))

    exclusion_patterns = {
        "individual": (r"individuals? (?:are )?not eligible", r"osoby fizyczne (?:nie są|nie sa) uprawnione", r"фізичні особи не (?:можуть|мають права)"),
        "company": (r"companies (?:are )?not eligible", r"przedsiębiorc\w* (?:nie są|nie sa) uprawn", r"компанії не (?:можуть|мають права)"),
    }
    for applicant, patterns in exclusion_patterns.items():
        for pattern in patterns:
            for match in re.finditer(pattern, lower, flags=re.I):
                add(Rule(f"exclude_applicant:{applicant}", "applicant_type", "excludes", applicant, _context(raw, match.start(), match.end()), 0.95))

    country_aliases = {
        "PL": ("poland", "polska", "polsce", "polski", "польщі", "польща"),
        "EU": ("european union", "eu member state", "member states of the eu", "unia europejska", "państwa członkowskie ue", "європейського союзу", "країнах єс"),
    }
    geo_markers = ("registered in", "established in", "based in", "resident in", "zarejestrowan", "siedzib", "zamieszka", "зареєстрован", "резидент", "прожива")
    for code, aliases in country_aliases.items():
        for alias in aliases:
            for match in re.finditer(re.escape(alias), lower):
                context = lower[max(0, match.start()-90):match.end()+90]
                if any(marker in context for marker in geo_markers):
                    add(Rule(f"geography:{code}", "geography", "contains", code, _context(raw, match.start(), match.end()), 0.82))

    age_patterns = [
        (r"(?:operating|established|registered|in business)\s+(?:for\s+)?(?:at least|minimum)\s+(\d{1,2})\s+years?", "gte"),
        (r"(?:no more than|maximum|less than)\s+(\d{1,2})\s+years?\s+(?:old|in operation)", "lte"),
        (r"(?:działa|prowadzi działalność|zarejestrowan\w*)\s+(?:od co najmniej|minimum)\s+(\d{1,2})\s+lat", "gte"),
        (r"(?:nie dłużej niż|maksymalnie)\s+(\d{1,2})\s+lat", "lte"),
        (r"(?:працює|зареєстрован\w*)\s+(?:щонайменше|мінімум)\s+(\d{1,2})\s+рок", "gte"),
        (r"(?:не більше|максимум)\s+(\d{1,2})\s+рок", "lte"),
    ]
    for pattern, operator in age_patterns:
        for match in re.finditer(pattern, lower, flags=re.I):
            add(Rule(f"company_age:{operator}", "company_age_years", operator, int(match.group(1)), _context(raw, match.start(), match.end()), 0.9))

    employee_patterns = [
        (r"(?:at least|minimum)\s+(\d{1,6})\s+(?:employees|staff)", "gte"),
        (r"(?:fewer than|less than|maximum|no more than)\s+(\d{1,6})\s+(?:employees|staff)", "lte"),
        (r"(?:co najmniej|min(?:imum)?)\s+(\d{1,6})\s+(?:pracowników|pracownik)", "gte"),
        (r"(?:mniej niż|maksymalnie|nie więcej niż)\s+(\d{1,6})\s+pracownik", "lte"),
        (r"(?:щонайменше|мінімум)\s+(\d{1,6})\s+працівник", "gte"),
        (r"(?:менше ніж|не більше|максимум)\s+(\d{1,6})\s+працівник", "lte"),
    ]
    for pattern, operator in employee_patterns:
        for match in re.finditer(pattern, lower, flags=re.I):
            add(Rule(f"employees:{operator}", "employees", operator, int(match.group(1)), _context(raw, match.start(), match.end()), 0.9))

    turnover_patterns = [
        (r"(?:annual )?(?:turnover|revenue)\s+(?:of )?(?:at least|minimum)\s+([\d.,\s]+)\s*(k|m|mln|tys|million|thousand)?\s*(pln|eur|usd|zł|zl|€|\$)", "gte"),
        (r"(?:annual )?(?:turnover|revenue)\s+(?:below|under|no more than|maximum)\s+([\d.,\s]+)\s*(k|m|mln|tys|million|thousand)?\s*(pln|eur|usd|zł|zl|€|\$)", "lte"),
        (r"(?:obrót|przychód)\s+(?:co najmniej|min(?:imum)?)\s+([\d.,\s]+)\s*(tys|mln)?\s*(pln|eur|zł|zl|€)", "gte"),
        (r"(?:obrót|przychód)\s+(?:poniżej|do|maksymalnie)\s+([\d.,\s]+)\s*(tys|mln)?\s*(pln|eur|zł|zl|€)", "lte"),
        (r"(?:оборот|виручк\w*)\s+(?:щонайменше|мінімум)\s+([\d.,\s]+)\s*(тис|млн)?\s*(pln|eur|usd|zł|€|\$)", "gte"),
    ]
    for pattern, operator in turnover_patterns:
        for match in re.finditer(pattern, lower, flags=re.I):
            value = _money_value(match.group(1), match.group(2))
            currency = _currency(match.group(3))
            if value is not None and currency:
                add(Rule(f"turnover:{operator}:{currency}", "annual_turnover", operator, {"amount": value, "currency": currency}, _context(raw, match.start(), match.end()), 0.9))

    contribution_patterns = [
        r"(?:own contribution|co-?financing)\s+(?:of |at least |minimum )?(\d{1,3}(?:[.,]\d+)?)\s*%",
        r"(?:wkład własny|wklad wlasny)\s+(?:co najmniej|min(?:imum)? )?(\d{1,3}(?:[.,]\d+)?)\s*%",
        r"(?:власний внесок|співфінансування)\s+(?:щонайменше|мінімум)?\s*(\d{1,3}(?:[.,]\d+)?)\s*%",
    ]
    for pattern in contribution_patterns:
        for match in re.finditer(pattern, lower, flags=re.I):
            value = _num(match.group(1))
            if value is not None and 0 <= value <= 100:
                add(Rule("own_contribution:gte", "own_contribution_percent", "gte", value, _context(raw, match.start(), match.end()), 0.92))

    individual_age_patterns = [
        (r"(?:applicants?|participants?)\s+(?:must be )?(?:at least|aged)\s+(\d{1,2})\+?", "gte"),
        (r"(?:under|below|younger than)\s+(\d{1,2})\s+years?", "lt"),
        (r"(?:co najmniej|ukończone)\s+(\d{1,2})\s+lat", "gte"),
        (r"(?:poniżej|mniej niż)\s+(\d{1,2})\s+lat", "lt"),
        (r"(?:щонайменше|не менше)\s+(\d{1,2})\s+рок", "gte"),
        (r"(?:до|молодше)\s+(\d{1,2})\s+рок", "lt"),
    ]
    for pattern, operator in individual_age_patterns:
        for match in re.finditer(pattern, lower, flags=re.I):
            add(Rule(f"person_age:{operator}", "person_age", operator, int(match.group(1)), _context(raw, match.start(), match.end()), 0.8))

    status_patterns = {
        "unemployed": (r"must be unemployed", r"osob\w* bezrobotn", r"безробітн"),
        "employed": (r"must be employed", r"osob\w* zatrudnion", r"працевлаштован"),
    }
    for value, patterns in status_patterns.items():
        for pattern in patterns:
            for match in re.finditer(pattern, lower, flags=re.I):
                add(Rule(f"employment:{value}", "employment_status", "eq", value, _context(raw, match.start(), match.end()), 0.85))

    return [rule.__dict__.copy() for rule in rules]


def compile_eligibility_profile(query: object, *, country: object = "EU", base_profile: dict | None = None) -> dict:
    """Extract only user facts explicitly present in the request/current profile."""
    raw = _clean(query, 8000)
    lower = raw.casefold()
    profile = dict(base_profile or {})
    profile.setdefault("country", str(country or "EU").upper())
    profile.setdefault("applicant_types", list(profile.get("applicant_types") or []))
    facts: dict[str, Any] = {}

    if profile.get("applicant_types"):
        facts["applicant_type"] = list(profile["applicant_types"])

    geography_patterns = {
        "PL": (r"(?:resident|registered|based|live|living)\s+in\s+poland", r"(?:mieszkam|rezydent|zarejestrowan\w*)\s+(?:w\s+)?polsce", r"(?:живу|резидент|зареєстрован\w*)\s+(?:у|в)\s*польщ"),
        "EU": (r"(?:resident|registered|based)\s+in\s+(?:the )?eu", r"(?:rezydent|zarejestrowan\w*)\s+w\s+ue", r"(?:резидент|зареєстрован\w*)\s+(?:у|в)\s*єс"),
    }
    geos = []
    for code, patterns in geography_patterns.items():
        if any(re.search(pattern, lower, flags=re.I) for pattern in patterns):
            geos.append(code)
    if geos:
        facts["geography"] = geos

    company_age_patterns = (
        r"(?:company|business)\s+(?:is\s+)?(\d{1,2})\s+years?\s+old",
        r"(?:firma|działalność|dzialalnosc)\s+(?:ma|działa od)\s+(\d{1,2})\s+lat",
        r"(?:компані\w*|бізнес\w*)\s+(\d{1,2})\s+рок",
    )
    for pattern in company_age_patterns:
        match = re.search(pattern, lower, flags=re.I)
        if match:
            facts["company_age_years"] = int(match.group(1)); break

    employee_patterns = (
        r"(?:we have|company has|team of)\s+(\d{1,6})\s+(?:employees|staff|people)",
        r"(?:mamy|firma ma)\s+(\d{1,6})\s+pracownik",
        r"(?:маємо|компанія має)\s+(\d{1,6})\s+працівник",
    )
    for pattern in employee_patterns:
        match = re.search(pattern, lower, flags=re.I)
        if match:
            facts["employees"] = int(match.group(1)); break

    turnover_patterns = (
        r"(?:our |annual )?(?:turnover|revenue)\s+(?:is\s+)?([\d.,\s]+)\s*(k|m|mln|tys|million|thousand)?\s*(pln|eur|usd|zł|zl|€|\$)",
        r"(?:nasz |roczny )?(?:obrót|przychód)\s+(?:to\s+)?([\d.,\s]+)\s*(tys|mln)?\s*(pln|eur|zł|zl|€)",
        r"(?:наш |річний )?(?:оборот|дохід|виручк\w*)\s+([\d.,\s]+)\s*(тис|млн)?\s*(pln|eur|usd|zł|€|\$)",
    )
    for pattern in turnover_patterns:
        match = re.search(pattern, lower, flags=re.I)
        if match:
            value = _money_value(match.group(1), match.group(2))
            currency = _currency(match.group(3))
            if value is not None and currency:
                facts["annual_turnover"] = {"amount": value, "currency": currency}; break

    contribution_patterns = (
        r"(?:i can contribute|own contribution available|can provide)\s+(\d{1,3}(?:[.,]\d+)?)\s*%",
        r"(?:mogę wnieść|moge wniesc|mam wkład własny|mam wklad wlasny)\s+(\d{1,3}(?:[.,]\d+)?)\s*%",
        r"(?:можу внести|маю власний внесок)\s+(\d{1,3}(?:[.,]\d+)?)\s*%",
    )
    for pattern in contribution_patterns:
        match = re.search(pattern, lower, flags=re.I)
        if match:
            value = _num(match.group(1))
            if value is not None and 0 <= value <= 100:
                facts["own_contribution_percent"] = value; break

    person_age_patterns = (
        r"(?:i am|i'm)\s+(\d{1,2})\s*(?:years? old)?",
        r"mam\s+(\d{1,2})\s+lat",
        r"мені\s+(\d{1,2})\s+рок",
    )
    for pattern in person_age_patterns:
        match = re.search(pattern, lower, flags=re.I)
        if match:
            age = int(match.group(1))
            if 14 <= age <= 100:
                facts["person_age"] = age; break

    if re.search(r"\b(?:i am unemployed|bezrobotn\w*|безробітн\w*)\b", lower, flags=re.I):
        facts["employment_status"] = "unemployed"
    elif re.search(r"\b(?:i am employed|zatrudnion\w*|працевлаштован\w*)\b", lower, flags=re.I):
        facts["employment_status"] = "employed"

    return {
        "version": MONEY_ELIGIBILITY_VERSION,
        "facts": facts,
        "known_fields": sorted(facts),
        "source": "explicit_current_query_and_compiled_profile",
        "search_country": str(country or "EU").upper(),
        "truth_semantics": "profile_fact_not_present_means_unknown_not_false",
    }


def _compare(rule: dict, facts: dict) -> tuple[str, str]:
    field = rule["field"]
    operator = rule["operator"]
    expected = rule["value"]
    if field not in facts:
        return "unknown", f"missing_profile_fact:{field}"
    actual = facts[field]

    if field == "applicant_type":
        values = set(actual if isinstance(actual, list) else [actual])
        if operator == "contains": return ("pass", "applicant_type_match") if expected in values else ("fail", "applicant_type_mismatch")
        if operator == "excludes": return ("fail", "excluded_applicant_type") if expected in values else ("pass", "excluded_type_not_present")
    if field == "geography":
        values = set(actual if isinstance(actual, list) else [actual])
        if expected == "EU" and "PL" in values:
            return "pass", "member_state_geography_match"
        return ("pass", "geography_match") if expected in values else ("fail", "geography_mismatch")
    if field == "annual_turnover":
        if not isinstance(actual, dict) or actual.get("currency") != expected.get("currency"):
            return "unknown", "turnover_currency_not_comparable"
        actual, expected = actual.get("amount"), expected.get("amount")
    try:
        if operator == "gte": return ("pass", "numeric_requirement_met") if float(actual) >= float(expected) else ("fail", "numeric_requirement_not_met")
        if operator == "lte": return ("pass", "numeric_requirement_met") if float(actual) <= float(expected) else ("fail", "numeric_requirement_not_met")
        if operator == "lt": return ("pass", "numeric_requirement_met") if float(actual) < float(expected) else ("fail", "numeric_requirement_not_met")
    except (TypeError, ValueError):
        return "unknown", f"non_numeric_profile_fact:{field}"
    if operator == "eq": return ("pass", "exact_requirement_met") if actual == expected else ("fail", "exact_requirement_not_met")
    return "unknown", "unsupported_operator"


def evaluate_eligibility(rules: list[dict], profile: dict) -> dict:
    facts = dict((profile or {}).get("facts") or {})
    checks = []
    for rule in rules or []:
        state, reason = _compare(rule, facts)
        checks.append({
            "rule_id": rule.get("id"), "field": rule.get("field"), "operator": rule.get("operator"),
            "expected": rule.get("value"), "profile_value": facts.get(rule.get("field")),
            "state": state, "reason": reason, "evidence": rule.get("evidence"),
            "confidence": rule.get("confidence"), "mandatory": bool(rule.get("mandatory", True)),
        })
    mandatory = [c for c in checks if c["mandatory"]]
    failed = [c for c in mandatory if c["state"] == "fail"]
    unknown = [c for c in mandatory if c["state"] == "unknown"]
    passed = [c for c in mandatory if c["state"] == "pass"]
    if failed:
        state = "ineligible"
    elif mandatory and not unknown and len(passed) == len(mandatory):
        state = "eligible_candidate"
    elif mandatory and passed:
        state = "possible"
    else:
        state = "unknown"
    missing_fields = sorted({c["field"] for c in unknown if c.get("field")})
    return {
        "version": MONEY_ELIGIBILITY_VERSION,
        "state": state,
        "rules_observed": len(rules or []),
        "mandatory_rules": len(mandatory),
        "passed": len(passed),
        "failed": len(failed),
        "unknown": len(unknown),
        "missing_profile_fields": missing_fields,
        "checks": checks,
        "legal_eligibility_verified": False,
        "award_probability_inferred": False,
        "truth_semantics": "eligible_candidate_means_all_observed_rules_match_not_all_legal_rules_known",
    }


def enrich_record_eligibility(record: dict, *, source_text: object = "", profile: dict) -> dict:
    output = dict(record or {})
    rules = extract_eligibility_rules(source_text)
    evaluation = evaluate_eligibility(rules, profile)
    output["eligibility_rules"] = rules
    output["eligibility"] = evaluation
    output["eligibility_state"] = evaluation["state"]
    output["likely_eligible"] = evaluation["state"] == "eligible_candidate"
    blockers = list(output.get("blockers") or [])
    unknowns = list(output.get("unknown_requirements") or [])
    for check in evaluation["checks"]:
        if check["state"] == "fail":
            token = f"eligibility:{check['rule_id']}"
            if token not in blockers: blockers.append(token)
    for field in evaluation["missing_profile_fields"]:
        token = f"eligibility_fact:{field}"
        if token not in unknowns: unknowns.append(token)
    output["blockers"] = blockers
    output["unknown_requirements"] = unknowns
    return output


def money_eligibility_capabilities() -> dict:
    return {
        "version": MONEY_ELIGIBILITY_VERSION,
        "states": ["eligible_candidate", "ineligible", "possible", "unknown"],
        "rule_fields": [
            "applicant_type", "geography", "company_age_years", "employees", "annual_turnover",
            "own_contribution_percent", "person_age", "employment_status",
        ],
        "explicit_profile_facts_only": True,
        "mixed_money_unit_abbreviations": ["k", "m", "tys", "mln", "тис", "млн", "thousand", "million"],
        "absence_means_false": False,
        "legal_eligibility_verified": False,
        "truth_semantics": "observed_rules_plus_explicit_profile_facts_only",
    }


__all__ = [
    "MONEY_ELIGIBILITY_VERSION", "compile_eligibility_profile", "enrich_record_eligibility",
    "evaluate_eligibility", "extract_eligibility_rules", "money_eligibility_capabilities",
]
