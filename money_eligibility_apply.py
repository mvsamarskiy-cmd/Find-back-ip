"""Apply Money Eligibility v2.2 to normalized money records."""
from __future__ import annotations

from copy import deepcopy

from money_eligibility import evaluate_eligibility, extract_eligibility_rules


ELIGIBILITY_APPLY_VERSION = "money-eligibility-apply-v2.2"


def _fallback_rules(record: dict) -> list[dict]:
    text = " ".join((str(record.get("title") or ""), str(record.get("description") or "")))
    return extract_eligibility_rules(text)


def _direct_rules(record: dict) -> list[dict]:
    verification = record.get("direct_verification") if isinstance(record.get("direct_verification"), dict) else {}
    rules = verification.get("eligibility_rules")
    return [dict(rule) for rule in rules if isinstance(rule, dict)] if isinstance(rules, list) else []


def _state_priority(state: str) -> int:
    return {"eligible_candidate": 0, "possible": 1, "unknown": 2, "ineligible": 3}.get(str(state), 2)


def _eligibility_score(evaluation: dict) -> int:
    state = evaluation.get("state")
    total = max(1, int(evaluation.get("mandatory_rules") or 0))
    passed = int(evaluation.get("passed") or 0)
    unknown = int(evaluation.get("unknown") or 0)
    if state == "ineligible": return 0
    if state == "eligible_candidate": return 100
    if state == "possible": return max(35, min(85, round(100 * passed / total - 8 * unknown)))
    return 25 if evaluation.get("rules_observed") else 15


def _compatible_geo(expected: str, actual_values: set[str]) -> bool:
    if expected in actual_values:
        return True
    if expected == "EU" and "PL" in actual_values:
        return True
    return False


def _alternative_check(field: str, rules: list[dict], profile: dict) -> dict:
    facts = dict((profile or {}).get("facts") or {})
    actual = facts.get(field)
    expected = [rule.get("value") for rule in rules]
    evidence = [rule.get("evidence") for rule in rules if rule.get("evidence")]
    if actual is None:
        return {
            "rule_id": f"{field}:one_of", "field": field, "operator": "one_of", "expected": expected,
            "profile_value": None, "state": "unknown", "reason": f"missing_profile_fact:{field}",
            "evidence": evidence, "confidence": max([float(rule.get("confidence") or 0) for rule in rules] or [0]),
            "mandatory": True,
        }
    values = set(actual if isinstance(actual, list) else [actual])
    matched = any(_compatible_geo(str(item), values) for item in expected) if field == "geography" else bool(values & set(expected))
    return {
        "rule_id": f"{field}:one_of", "field": field, "operator": "one_of", "expected": expected,
        "profile_value": actual, "state": "pass" if matched else "fail",
        "reason": f"{field}_alternative_match" if matched else f"{field}_alternative_mismatch",
        "evidence": evidence, "confidence": max([float(rule.get("confidence") or 0) for rule in rules] or [0]),
        "mandatory": True,
    }


def _evaluate_grouped(rules: list[dict], profile: dict) -> dict:
    """Treat allowed applicant/geography values as OR groups; all other rules remain AND."""
    grouped, remaining = {}, []
    for rule in rules or []:
        field = rule.get("field")
        operator = rule.get("operator")
        if field in {"applicant_type", "geography"} and operator == "contains":
            grouped.setdefault(field, []).append(rule)
        else:
            remaining.append(rule)

    base = evaluate_eligibility(remaining, profile)
    checks = list(base.get("checks") or [])
    for field, alternatives in grouped.items():
        checks.append(_alternative_check(field, alternatives, profile))

    mandatory = [check for check in checks if check.get("mandatory", True)]
    failed = [check for check in mandatory if check.get("state") == "fail"]
    unknown = [check for check in mandatory if check.get("state") == "unknown"]
    passed = [check for check in mandatory if check.get("state") == "pass"]
    if failed:
        state = "ineligible"
    elif mandatory and not unknown and len(passed) == len(mandatory):
        state = "eligible_candidate"
    elif mandatory and passed:
        state = "possible"
    else:
        state = "unknown"
    missing = sorted({check.get("field") for check in unknown if check.get("field")})
    return {
        "version": base.get("version"),
        "state": state,
        "rules_observed": len(rules or []),
        "mandatory_rules": len(mandatory),
        "passed": len(passed),
        "failed": len(failed),
        "unknown": len(unknown),
        "missing_profile_fields": missing,
        "checks": checks,
        "alternative_groups": {field: [rule.get("value") for rule in alternatives] for field, alternatives in grouped.items()},
        "legal_eligibility_verified": False,
        "award_probability_inferred": False,
        "truth_semantics": "eligible_candidate_means_all_observed_rule_groups_match_not_all_legal_rules_known",
    }


def _adjust_record(record: dict, evaluation: dict, rules: list[dict], evidence_level: str) -> dict:
    row = deepcopy(record)
    row["eligibility_rules"] = rules
    row["eligibility"] = evaluation
    row["eligibility_state"] = evaluation["state"]
    row["eligibility_evidence_level"] = evidence_level
    row["eligibility_score"] = _eligibility_score(evaluation)
    row["likely_eligible"] = evaluation["state"] == "eligible_candidate"

    blockers = list(row.get("blockers") or [])
    unknowns = list(row.get("unknown_requirements") or [])
    for check in evaluation.get("checks") or []:
        if check.get("state") == "fail":
            token = f"eligibility:{check.get('rule_id')}"
            if token not in blockers: blockers.append(token)
    for field in evaluation.get("missing_profile_fields") or []:
        token = f"eligibility_fact:{field}"
        if token not in unknowns: unknowns.append(token)
    row["blockers"] = blockers
    row["unknown_requirements"] = unknowns

    ranking = deepcopy(row.get("practical_ranking") or {})
    components = dict(ranking.get("components") or {})
    components["eligibility"] = row["eligibility_score"]
    ranking["components"] = components
    old_score = int(ranking.get("score") or 0)
    if evaluation["state"] == "ineligible":
        ranking["score"] = min(old_score, 15)
    elif evaluation["state"] == "eligible_candidate":
        ranking["score"] = min(100, round(old_score * 0.85 + 15))
    elif evaluation["state"] == "possible":
        ranking["score"] = round(old_score * 0.92 + row["eligibility_score"] * 0.08)
    else:
        ranking["score"] = old_score
    ranking["eligibility_adjustment_version"] = ELIGIBILITY_APPLY_VERSION
    row["practical_ranking"] = ranking
    return row


def apply_eligibility_to_payload(payload: dict, *, eligibility_profile: dict) -> dict:
    output = dict(payload or {})
    records = []
    for record in output.get("money_records") or []:
        if not isinstance(record, dict):
            continue
        direct = _direct_rules(record)
        rules = direct or _fallback_rules(record)
        evidence_level = "direct_source" if direct else "retrieval_snippet"
        evaluation = _evaluate_grouped(rules, eligibility_profile or {})
        records.append(_adjust_record(record, evaluation, rules, evidence_level))

    records.sort(key=lambda row: (
        _state_priority(row.get("eligibility_state")),
        -int((row.get("practical_ranking") or {}).get("score") or 0),
        -int(row.get("evidence_score") or 0),
        str(row.get("title") or "").casefold(),
    ))
    output["money_records"] = records
    output["eligibility_profile"] = eligibility_profile
    summary = {state: 0 for state in ("eligible_candidate", "possible", "unknown", "ineligible")}
    missing = {}
    for record in records:
        state = record.get("eligibility_state") or "unknown"
        summary[state] = summary.get(state, 0) + 1
        for field in (record.get("eligibility") or {}).get("missing_profile_fields") or []:
            missing[field] = missing.get(field, 0) + 1
    output["eligibility_summary"] = {
        "states": summary,
        "missing_profile_fields": dict(sorted(missing.items(), key=lambda item: (-item[1], item[0]))),
        "version": ELIGIBILITY_APPLY_VERSION,
        "truth_semantics": "candidate_state_based_only_on_observed_rules_and_explicit_profile_facts",
    }
    return output


def eligibility_apply_capabilities() -> dict:
    return {
        "version": ELIGIBILITY_APPLY_VERSION,
        "direct_source_rules_preferred": True,
        "snippet_rules_fallback": True,
        "alternative_applicant_and_geography_rules_are_or_groups": True,
        "ineligible_requires_observed_rule_failure": True,
        "eligible_candidate_requires_all_observed_mandatory_rule_groups_pass": True,
        "unknown_profile_fields_preserved": True,
        "legal_eligibility_verified": False,
    }


__all__ = ["ELIGIBILITY_APPLY_VERSION", "apply_eligibility_to_payload", "eligibility_apply_capabilities"]
