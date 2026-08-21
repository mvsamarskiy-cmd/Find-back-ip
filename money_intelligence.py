"""Evidence-aware normalization/ranking for Money Opportunity Intelligence v2."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from urllib.parse import urlsplit

from money_sources import source_affinity, source_for_host
from money_taxonomy import TYPE_BY_ID, infer_money_types
from opportunity_intelligence import extract_amount, extract_deadline, extract_eligibility, infer_status


MONEY_INTELLIGENCE_VERSION = "money-intelligence-v2"


def _clean(value: object, limit: int = 8000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _host(url: object) -> str:
    try:
        return (urlsplit(str(url or "")).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _source_tier(row: dict) -> str:
    source = source_for_host(row.get("url") or row.get("host"))
    if source:
        return source["tier"]
    return str(row.get("source_tier") or "web")


def classify_money_type(row: dict, *, profile: dict | None = None) -> tuple[str, str]:
    text = " ".join((str(row.get("title") or ""), str(row.get("description") or "")))
    matches = infer_money_types(text, limit=6)
    if matches:
        item = TYPE_BY_ID[matches[0]]
        return item.id, item.family
    source = source_for_host(row.get("url") or row.get("host"))
    requested_types = list((profile or {}).get("requested_types") or [])
    if source:
        source_types = list(source.get("types") or [])
        for requested in requested_types:
            if requested in source_types:
                item = TYPE_BY_ID[requested]
                return item.id, item.family
        if source_types:
            item = TYPE_BY_ID.get(source_types[0])
            if item:
                return item.id, item.family
        source_families = list(source.get("families") or [])
        if source_families:
            return "other_monetizable_signal", source_families[0]
    if requested_types:
        item = TYPE_BY_ID[requested_types[0]]
        return item.id, item.family
    return "other_monetizable_signal", "other"


def _extract_percent(text: str) -> dict | None:
    hits = []
    for match in re.finditer(r"(?<!\d)(\d{1,3}(?:[.,]\d{1,2})?)\s*%", text):
        try:
            value = float(match.group(1).replace(",", "."))
        except ValueError:
            continue
        if 0 <= value <= 100:
            left, right = max(0, match.start() - 70), min(len(text), match.end() + 70)
            hits.append({"value": value, "evidence": _clean(text[left:right], 180)})
    return hits[0] if hits else None


def extract_economics(text: object, type_id: str) -> dict:
    raw = _clean(text, 30000)
    lower = raw.casefold()
    type_meta = TYPE_BY_ID.get(type_id, TYPE_BY_ID["other_monetizable_signal"])
    amount = extract_amount(raw)
    rate = _extract_percent(raw)
    cofinancing = any(term in lower for term in (
        "co-financing", "cofinancing", "own contribution", "wkład własny", "wklad wlasny",
        "współfinans", "wspolfinans", "власн\u0438\u0439 внесок", "співфінанс",
    ))
    reimbursement = any(term in lower for term in ("reimburse", "refundac", "zwrot koszt", "відшкодуван"))
    equity = type_meta.economic_kind in {"equity", "equity_or_reward"}
    return {
        "economic_kind": type_meta.economic_kind,
        "amount": amount,
        "repayable": type_meta.repayable,
        "rate_percent_observed": rate,
        "cofinancing_mentioned": cofinancing,
        "reimbursement_mentioned": reimbursement,
        "equity_dilution_possible": True if equity else None,
        "transaction_costs_verified": False,
        "profit_guaranteed": False,
    }


def _status_value(status: dict) -> str:
    value = str((status or {}).get("value") or "unknown")
    return "upcoming" if value == "open_or_upcoming" else value if value in {"open", "upcoming", "closed", "unknown"} else "unknown"


def _evidence_score(row: dict, verification: dict, *, family: str, type_id: str) -> int:
    tier = _source_tier(row)
    score = {"official": 70, "public": 62, "platform": 48, "market": 42, "web": 32, "tor": 30}.get(tier, 30)
    if verification.get("source_verified"):
        score += 15
    if row.get("onion_service"):
        # Onion origin is provenance, not quality.
        score += 0
    score += min(15, source_affinity(row.get("url") or row.get("host"), families=[family], types=[type_id])) // 2
    return max(0, min(100, score))


def _fit_components(row: dict, profile: dict, *, type_id: str, family: str, eligibility: dict, economics: dict, status_value: str) -> tuple[int, list[str], list[str]]:
    score, blockers, unknowns = 45, [], []
    requested_types = set(profile.get("requested_types") or [])
    requested_families = set(profile.get("requested_families") or [])
    if requested_types:
        score += 20 if type_id in requested_types else 3
    elif requested_families:
        score += 15 if family in requested_families else 4
    else:
        score += 8

    requested_applicants = set(profile.get("applicant_types") or [])
    observed_applicants = set(eligibility.get("applicant_types") or [])
    if requested_applicants:
        if requested_applicants & observed_applicants:
            score += 12
        elif observed_applicants:
            blockers.append("applicant_type_unmatched")
            score -= 18
        else:
            unknowns.append("applicant_eligibility")
    else:
        unknowns.append("applicant_profile")

    if status_value == "closed":
        blockers.append("closed")
        score -= 35
    elif status_value == "open":
        score += 12
    elif status_value == "upcoming":
        score += 7
    else:
        unknowns.append("current_status")

    requested_amount = profile.get("requested_amount") or {}
    observed_amount = economics.get("amount") or {}
    if requested_amount and requested_amount.get("max"):
        if observed_amount and observed_amount.get("currency") == requested_amount.get("currency"):
            if int(observed_amount.get("max") or 0) >= int(requested_amount.get("max") or 0):
                score += 10
            else:
                blockers.append("amount_below_requested")
                score -= 10
        else:
            unknowns.append("amount_comparability")
    elif not observed_amount:
        unknowns.append("amount")

    return max(0, min(100, score)), blockers, unknowns


def _economic_upside_score(economics: dict, profile: dict) -> int:
    amount = economics.get("amount") or {}
    requested = profile.get("requested_amount") or {}
    if amount.get("max") is None:
        return 40
    if requested.get("max") and amount.get("currency") == requested.get("currency"):
        ratio = float(amount.get("max") or 0) / max(1.0, float(requested.get("max") or 1))
        return 85 if ratio >= 1 else 60 if ratio >= 0.5 else 35
    return 62


def _practical_score(*, evidence: int, fit: int, economics: int, status_value: str, type_id: str) -> dict:
    meta = TYPE_BY_ID.get(type_id, TYPE_BY_ID["other_monetizable_signal"])
    status_score = {"open": 90, "upcoming": 70, "unknown": 42, "closed": 0}.get(status_value, 42)
    speed = meta.speed * 20
    effort_cost = (meta.effort - 1) * 8
    capital_cost = (meta.capital_required - 1) * 7
    competition_cost = (meta.competition - 1) * 6
    raw = (
        evidence * 0.24 + fit * 0.27 + economics * 0.18 + status_score * 0.15 + speed * 0.16
        - effort_cost * 0.35 - capital_cost * 0.25 - competition_cost * 0.20
    )
    total = max(0, min(100, round(raw)))
    return {
        "score": total,
        "components": {
            "evidence": evidence,
            "fit": fit,
            "economic_upside": economics,
            "status_freshness": status_score,
            "speed_prior": speed,
            "effort_prior_1_5": meta.effort,
            "capital_required_prior_1_5": meta.capital_required,
            "competition_prior_1_5": meta.competition,
        },
        "formula_version": "explainable-weighted-v2",
        "guaranteed_return": False,
    }


def _opportunity_id(title: str, host: str, type_id: str) -> str:
    basis = "|".join((_clean(title, 500).casefold(), host.casefold(), type_id))
    return "mo_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:18]


def _fingerprint(title: str, type_id: str) -> str:
    tokens = re.findall(r"[a-z0-9ąćęłńóśźżа-яіїєґ]{3,}", _clean(title, 500).casefold(), flags=re.I)
    stable = " ".join(tokens[:14])
    return hashlib.sha256(f"{type_id}|{stable}".encode("utf-8")).hexdigest()[:20]


def normalize_money_row(row: dict, *, profile: dict) -> dict:
    source_row = dict(row or {})
    title = _clean(source_row.get("title"), 400)
    description = _clean(source_row.get("description"), 4000)
    url = _clean(source_row.get("url"), 2000)
    host = _host(url) or _clean(source_row.get("host"), 260)
    type_id, family = classify_money_type(source_row, profile=profile)

    existing_opportunity = source_row.get("opportunity") if isinstance(source_row.get("opportunity"), dict) else {}
    existing_verification = existing_opportunity.get("verification") if isinstance(existing_opportunity.get("verification"), dict) else {}
    verification = dict(existing_verification)
    if not verification and isinstance(source_row.get("verification"), dict):
        verification = dict(source_row["verification"])

    evidence_text = " ".join((title, description))
    deadline = existing_opportunity.get("deadline") or extract_deadline(evidence_text)
    eligibility = existing_opportunity.get("eligibility") or extract_eligibility(evidence_text)
    status = existing_opportunity.get("status") or infer_status(evidence_text, deadline)
    status_value = _status_value(status)
    economics = extract_economics(evidence_text, type_id)
    if not economics.get("amount") and existing_opportunity.get("amount"):
        economics["amount"] = existing_opportunity.get("amount")

    evidence_score = _evidence_score(source_row, verification, family=family, type_id=type_id)
    fit_score, blockers, unknowns = _fit_components(
        source_row, profile, type_id=type_id, family=family, eligibility=eligibility,
        economics=economics, status_value=status_value,
    )
    economic_score = _economic_upside_score(economics, profile)
    ranking = _practical_score(
        evidence=evidence_score, fit=fit_score, economics=economic_score,
        status_value=status_value, type_id=type_id,
    )
    source = source_for_host(url or host)
    official = bool(source and source.get("tier") == "official") or bool(source_row.get("official_source"))
    likely_eligible = bool(fit_score >= 72 and not blockers and "applicant_eligibility" not in unknowns)

    return {
        "opportunity_id": _opportunity_id(title, host, type_id),
        "dedupe_fingerprint": _fingerprint(title, type_id),
        "title": title,
        "description": description,
        "opportunity_type": type_id,
        "family": family,
        "funder_or_counterparty": (source or {}).get("name") or source_row.get("source_name") or host,
        "economics": economics,
        "amount": economics.get("amount"),
        "repayable": economics.get("repayable"),
        "eligible_applicants": eligibility.get("applicant_types") or [],
        "geography": eligibility.get("geography") or [],
        "deadline": (deadline or {}).get("date") if isinstance(deadline, dict) else None,
        "deadline_evidence": deadline,
        "status": status_value,
        "status_evidence": status,
        "official_url": url if official else None,
        "source_urls": [url] if url else [],
        "official_source": official,
        "current_call_verified": False,
        "source_observed": bool(verification.get("source_verified")),
        "verification": verification,
        "eligibility_state": "likely_eligible_candidate" if likely_eligible else "unknown_or_needs_check",
        "likely_eligible": likely_eligible,
        "fit_score": fit_score,
        "evidence_score": evidence_score,
        "practical_ranking": ranking,
        "blockers": blockers,
        "unknown_requirements": unknowns,
        "competition_signal": {"state": "prior_only", "value_1_5": TYPE_BY_ID[type_id].competition},
        "speed_to_money": {"state": "prior_only", "value_1_5": TYPE_BY_ID[type_id].speed},
        "action_steps": [
            "Open the original source and confirm the opportunity still exists.",
            "Confirm deadline/current status and authoritative rules.",
            "Check applicant, geography and co-financing requirements against the user's real profile.",
            "Confirm net economics, costs, taxes/fees and any repayment/equity obligations before acting.",
        ],
        "retrieval": {
            "provider_score": source_row.get("retrieval_score"),
            "transport": source_row.get("transport") or "web",
            "onion_service": bool(source_row.get("onion_service")),
            "query_index": source_row.get("query_index"),
            "query_lane": source_row.get("query_lane"),
        },
        "truth_semantics": "discovered_candidate_not_verified_availability_eligibility_or_profit",
    }


def _merge_duplicate(primary: dict, duplicate: dict) -> dict:
    merged = dict(primary)
    merged["source_urls"] = list(dict.fromkeys([*(primary.get("source_urls") or []), *(duplicate.get("source_urls") or [])]))[:20]
    merged["duplicate_evidence_count"] = int(primary.get("duplicate_evidence_count") or 1) + 1
    merged["evidence_score"] = max(int(primary.get("evidence_score") or 0), int(duplicate.get("evidence_score") or 0))
    if int((duplicate.get("practical_ranking") or {}).get("score") or 0) > int((primary.get("practical_ranking") or {}).get("score") or 0):
        merged["practical_ranking"] = duplicate.get("practical_ranking")
    merged["official_source"] = bool(primary.get("official_source") or duplicate.get("official_source"))
    merged["source_observed"] = bool(primary.get("source_observed") or duplicate.get("source_observed"))
    return merged


def normalize_money_payload(payload: dict, *, profile: dict) -> dict:
    result = dict(payload or {})
    records = [normalize_money_row(row, profile=profile) for row in (result.get("results") or []) if isinstance(row, dict)]
    deduped: dict[str, dict] = {}
    for record in records:
        key = record["dedupe_fingerprint"]
        if key not in deduped:
            record["duplicate_evidence_count"] = 1
            deduped[key] = record
        else:
            deduped[key] = _merge_duplicate(deduped[key], record)
    records = list(deduped.values())
    records.sort(key=lambda item: (
        -int((item.get("practical_ranking") or {}).get("score") or 0),
        -int(item.get("evidence_score") or 0),
        item.get("title", "").casefold(),
    ))

    family_summary = {}
    for record in records:
        family = record["family"]
        bucket = family_summary.setdefault(family, {"found": 0, "open": 0, "upcoming": 0, "likely_eligible": 0, "official_source": 0})
        bucket["found"] += 1
        if record["status"] in {"open", "upcoming"}:
            bucket[record["status"]] += 1
        if record["likely_eligible"]:
            bucket["likely_eligible"] += 1
        if record["official_source"]:
            bucket["official_source"] += 1

    result["money_records"] = records
    result["money_summary"] = family_summary
    result["money_profile"] = profile
    result["money_intelligence_version"] = MONEY_INTELLIGENCE_VERSION
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["truth_note"] = (
        "Money records are discovered candidates. Discovery is not current-call verification, eligibility, award, availability, arbitrage or profit proof. "
        "Open original sources and verify current rules/economics before acting."
    )
    return result


def money_intelligence_capabilities() -> dict:
    return {
        "version": MONEY_INTELLIGENCE_VERSION,
        "normalized_fields": [
            "opportunity_type", "family", "amount", "repayable", "status", "deadline",
            "eligible_applicants", "geography", "fit_score", "evidence_score", "practical_ranking",
            "blockers", "unknown_requirements", "source_urls", "action_steps",
        ],
        "cross_source_dedupe": True,
        "explainable_ranking": True,
        "current_call_verification_inferred": False,
        "guaranteed_profit_claims": False,
        "truth_semantics": "discovery_not_verification_not_guarantee",
    }


__all__ = [
    "MONEY_INTELLIGENCE_VERSION", "classify_money_type", "extract_economics",
    "money_intelligence_capabilities", "normalize_money_payload", "normalize_money_row",
]
