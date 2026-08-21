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
    if state == "ineligible":
        return 0
    if state == "eligible_candidate":
        return 100
    if state == "possible":
        return max(35, min(85, round(100 * passed / total - 8 * unknown)))
    return 25 if evaluation.get("rules_observed") else 15


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
            if token not in blockers:
                blockers.append(token)
    for field in evaluation.get("missing_profile_fields") or []:
        token = f"eligibility_fact:{field}"
        if token not in unknowns:
            unknowns.append(token)
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
        evaluation = evaluate_eligibility(rules, eligibility_profile or {})
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
        "ineligible_requires_observed_rule_failure": True,
        "eligible_candidate_requires_all_observed_mandatory_rules_pass": True,
        "unknown_profile_fields_preserved": True,
        "legal_eligibility_verified": False,
    }


__all__ = ["ELIGIBILITY_APPLY_VERSION", "apply_eligibility_to_payload", "eligibility_apply_capabilities"]
