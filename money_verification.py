"""Direct-source verification for Money / Material Opportunity Intelligence.

This layer reuses the hardened read-only Browser Eye evidence transport. It can
confirm that a page was observed and extract current page evidence, but it does
not prove legal eligibility, award probability, product availability or profit.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable

from money_sources import source_for_host
from opportunity_intelligence import extract_amount, extract_deadline, extract_eligibility, infer_status
from research_evidence import fetch_research_evidence


MONEY_VERIFICATION_VERSION = "money-direct-verification-v1"
DEFAULT_VERIFY_LIMIT = 3
MAX_VERIFY_LIMIT = 5


def _clean(value: object, limit: int = 2000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _verification_candidate(row: dict) -> tuple:
    source = source_for_host(row.get("url") or row.get("host"))
    tier = (source or {}).get("tier") or row.get("source_tier") or "web"
    tier_rank = {"official": 0, "public": 1, "platform": 2, "market": 3, "web": 4, "tor": 5}.get(str(tier), 6)
    return (
        tier_rank,
        -int(row.get("official_source") or False),
        -int(row.get("retrieval_score") or 0),
        int(row.get("query_index") or 0),
    )


def _is_program_like(row: dict) -> bool:
    return str(row.get("category") or "") in {
        "grant", "subsidy", "public_aid", "eu_fund", "regional_fund", "competition",
        "prize", "challenge", "bounty", "accelerator", "incubator", "scholarship",
        "fellowship", "research_funding", "corporate_open_call", "paid_open_call",
        "preferential_loan", "guarantee", "tax_relief", "reimbursement",
        "employment_incentive", "training_support", "export_support", "innovation_voucher",
        "green_energy_support", "procurement",
    }


def _active_program_verified(row: dict, evidence: dict, status: dict, deadline: dict | None) -> bool:
    """Conservative current-call confirmation for official/public program pages."""
    source = source_for_host(row.get("url") or row.get("host"))
    tier = (source or {}).get("tier")
    if tier not in {"official", "public"} or not _is_program_like(row):
        return False
    if evidence.get("provider_status") != "complete" or evidence.get("http_status") != 200:
        return False
    value = str((status or {}).get("value") or "unknown")
    reason = str((status or {}).get("reason") or "")
    if value in {"open", "upcoming"} and reason in {"open_marker", "upcoming_marker"}:
        return True
    if value == "open_or_upcoming" and reason == "future_deadline" and deadline and deadline.get("date"):
        return True
    return False


def verify_money_source(row: dict, *, evidence_fetcher: Callable = fetch_research_evidence) -> dict:
    url = str(row.get("url") or "").strip()
    checked_at = datetime.now(timezone.utc).isoformat()
    if not url:
        return {
            "version": MONEY_VERIFICATION_VERSION,
            "state": "missing_url",
            "source_observed": False,
            "current_call_verified": False,
            "checked_at": checked_at,
        }
    try:
        evidence = evidence_fetcher(url)
    except Exception:
        return {
            "version": MONEY_VERIFICATION_VERSION,
            "state": "evidence_error",
            "source_observed": False,
            "current_call_verified": False,
            "checked_at": checked_at,
        }
    if not isinstance(evidence, dict):
        evidence = {}
    state = str(evidence.get("provider_status") or "unknown")
    body = str(evidence.get("body_text") or "")[:50000]
    observed = state == "complete" and bool(body)
    amount = extract_amount(body) if observed else None
    deadline = extract_deadline(body) if observed else None
    eligibility = extract_eligibility(body) if observed else {
        "applicant_types": [], "individual_allowed": None, "company_required": None, "geography": []
    }
    status = infer_status(body, deadline) if observed else {
        "value": "unknown", "confidence": 0.0, "reason": "source_not_observed"
    }
    current_call_verified = _active_program_verified(row, evidence, status, deadline)
    return {
        "version": MONEY_VERIFICATION_VERSION,
        "state": "direct_source_observed" if observed else state,
        "source_observed": observed,
        "current_call_verified": current_call_verified,
        "http_status": evidence.get("http_status"),
        "requested_url": _clean(evidence.get("requested_url") or url, 2000),
        "final_url": _clean(evidence.get("final_url") or url, 2000),
        "observed_at": evidence.get("observed_at") or checked_at,
        "snapshot_sha256": evidence.get("snapshot_sha256"),
        "onion_service": bool(evidence.get("onion_service")),
        "onion_location": evidence.get("onion_location"),
        "amount": amount,
        "deadline": deadline,
        "eligibility": eligibility,
        "status": status,
        "public_contacts": evidence.get("public_contacts") or {},
        "truth_semantics": "direct_page_observation_not_legal_eligibility_or_profit_proof",
    }


def apply_money_verification(rows: list[dict], *, evidence_fetcher: Callable = fetch_research_evidence, limit: int = DEFAULT_VERIFY_LIMIT) -> list[dict]:
    """Verify a bounded top set concurrently and merge stronger direct evidence."""
    output = [dict(row) for row in rows if isinstance(row, dict)]
    limit = max(0, min(MAX_VERIFY_LIMIT, int(limit)))
    if not output or limit <= 0:
        return output
    indexes = sorted(range(len(output)), key=lambda index: _verification_candidate(output[index]))[:limit]
    verified: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=min(3, len(indexes))) as pool:
        futures = {pool.submit(verify_money_source, output[index], evidence_fetcher=evidence_fetcher): index for index in indexes}
        for future in as_completed(futures):
            index = futures[future]
            try:
                verified[index] = future.result()
            except Exception:
                verified[index] = {
                    "version": MONEY_VERIFICATION_VERSION,
                    "state": "verification_error",
                    "source_observed": False,
                    "current_call_verified": False,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }

    for index, verification in verified.items():
        row = output[index]
        row["money_direct_verification"] = verification
        if not verification.get("source_observed"):
            continue
        existing = row.get("opportunity") if isinstance(row.get("opportunity"), dict) else {}
        existing_verification = existing.get("verification") if isinstance(existing.get("verification"), dict) else {}
        source_verification = dict(existing_verification)
        source_verification.update({
            "source_verified": True,
            "state": "direct_source_observed",
            "http_status": verification.get("http_status"),
            "checked_at": verification.get("observed_at"),
            "snapshot_sha256": verification.get("snapshot_sha256"),
            "final_url": verification.get("final_url"),
            "verification_transport": "hardened_browser_eye_tor",
        })
        row["opportunity"] = {
            **existing,
            "amount": verification.get("amount") or existing.get("amount"),
            "deadline": verification.get("deadline") or existing.get("deadline"),
            "eligibility": verification.get("eligibility") or existing.get("eligibility"),
            "status": verification.get("status") or existing.get("status"),
            "verification": source_verification,
        }
    return output


def money_verification_capabilities() -> dict:
    return {
        "version": MONEY_VERIFICATION_VERSION,
        "default_verify_limit": DEFAULT_VERIFY_LIMIT,
        "max_verify_limit": MAX_VERIFY_LIMIT,
        "concurrent_max": 3,
        "transport": "hardened_browser_eye_tor",
        "current_call_verification": "official_or_public_program_page_plus_direct_active_evidence",
        "market_listing_availability_inferred": False,
        "legal_eligibility_inferred": False,
        "profit_inferred": False,
        "truth_semantics": "direct_source_observation_not_award_availability_or_profit_guarantee",
    }


__all__ = [
    "DEFAULT_VERIFY_LIMIT", "MAX_VERIFY_LIMIT", "MONEY_VERIFICATION_VERSION",
    "apply_money_verification", "money_verification_capabilities", "verify_money_source",
]
