"""Bounded query planner for Money / Material Opportunity Intelligence v2."""
from __future__ import annotations

import re

from money_sources import sources_for
from money_taxonomy import TYPE_BY_ID, infer_money_families, infer_money_types, looks_like_material_opportunity
from opportunity_intelligence import extract_amount


MONEY_QUERY_PLANNER_VERSION = "money-query-planner-v2"
MAX_MONEY_QUERY_LANES = 7


FAMILY_EXPANSIONS = {
    "funding": "grant subsidy public aid EU funds regional programme competition prize open call",
    "capital": "investor venture capital angel accelerator incubator equity crowdfunding",
    "finance": "preferential loan guarantee leasing factoring equipment financing working capital",
    "savings": "tax relief reimbursement employment incentive training support export support voucher energy support",
    "revenue": "procurement tender contract subcontract supplier wanted paid open call",
    "assets": "business for sale asset sale liquidation public auction distressed equipment real estate",
    "local": "local classifieds business offers equipment stock wholesale closeout",
    "markets": "price gap supply shortage import export opportunity market dislocation demand",
    "off_market": "public notices BIP bulletin liquidation insolvency university partner call local association off market",
    "other": "monetizable opportunity paid programme commercial opportunity",
}

NEED_FAMILY_HINTS = (
    ((r"\bequipment\b", r"\bmachin(?:e|ery)\b", r"\bsprz[eę]t\w*\b", r"\bmaszyn\w*\b", r"\bобладнан\w*\b"), ("funding", "finance", "assets", "revenue")),
    ((r"\bworking capital\b", r"\bkapita[łl] obrotow\w*\b", r"\bоборотн\w* капітал\w*\b"), ("finance", "capital", "revenue", "funding")),
    ((r"\bstartup\b", r"\bstart-up\b", r"\bстартап\w*\b"), ("funding", "capital", "finance", "revenue")),
    ((r"\bmanufactur\w*\b", r"\bprodukc\w*\b", r"\bвиробниц\w*\b"), ("funding", "finance", "revenue", "assets")),
    ((r"\bexport\w*\b", r"\beksport\w*\b", r"\bекспорт\w*\b"), ("savings", "revenue", "markets", "finance")),
    ((r"\breal estate\b", r"\bnieruchomo[śs]\w*\b", r"\bнерухом\w*\b"), ("assets", "local", "finance", "off_market")),
    ((r"\bjob\w*\b", r"\bcontract\w*\b", r"\bzlecen\w*\b", r"\bробот\w*\b", r"\bконтракт\w*\b"), ("revenue", "local", "off_market")),
)

APPLICANT_HINTS = {
    "individual": (r"\bindividual\w*\b", r"\bosob\w* fizyczn\w*\b", r"\bфізичн\w* особ\w*\b"),
    "startup": (r"\bstartup\w*\b", r"\bстартап\w*\b"),
    "sme": (r"\bsme\b", r"\bm[śs]p\b", r"\bмал\w* бізнес\w*\b"),
    "company": (r"\bcompany\b", r"\bfirma\w*\b", r"\bsp[oó][łl]k\w*\b", r"\bкомпан\w*\b", r"\bбізнес\w*\b"),
    "ngo": (r"\bngo\b", r"\bfundacj\w*\b", r"\bstowarzyszen\w*\b", r"\bнго\b", r"\bфонд\w*\b"),
}


def _clean(value: object, limit: int = 1800) -> str:
    return " ".join(str(value or "").split())[:limit]


def _country_name(country: object) -> str:
    code = str(country or "EU").strip().upper()
    return {
        "EU": "European Union", "PL": "Poland", "DE": "Germany", "FR": "France",
        "NL": "Netherlands", "DK": "Denmark", "NO": "Norway", "SE": "Sweden",
        "IE": "Ireland", "ES": "Spain", "IT": "Italy", "PT": "Portugal",
    }.get(code, code)


def _need_families(text: str) -> list[str]:
    output = []
    for patterns, families in NEED_FAMILY_HINTS:
        if any(re.search(pattern, text, flags=re.I) for pattern in patterns):
            for family in families:
                if family not in output:
                    output.append(family)
    return output


def _applicant_types(text: str) -> list[str]:
    return [name for name, patterns in APPLICANT_HINTS.items() if any(re.search(pattern, text, flags=re.I) for pattern in patterns)]


def compile_money_profile(query: object, *, country: object = "EU") -> dict:
    cleaned = _clean(query)
    text = cleaned.casefold()
    explicit_types = infer_money_types(cleaned, limit=12)
    explicit_families = infer_money_families(cleaned, limit=8)
    need_families = _need_families(text)
    families = []
    for family in [*explicit_families, *need_families]:
        if family not in families:
            families.append(family)
    amount = extract_amount(cleaned)
    return {
        "query": cleaned,
        "country": str(country or "EU").strip().upper(),
        "country_name": _country_name(country),
        "money_intent": looks_like_material_opportunity(cleaned),
        "requested_types": explicit_types,
        "requested_families": families,
        "applicant_types": _applicant_types(text),
        "requested_amount": amount,
    }


def _family_order(profile: dict) -> list[str]:
    requested = list(profile.get("requested_families") or [])
    if requested:
        # Keep exploration lanes after the inferred mechanisms so that an
        # equipment-finance request can still discover liquidation assets or
        # procurement revenue instead of being trapped in one mechanism.
        exploration = ["funding", "finance", "capital", "revenue", "assets", "savings", "local", "off_market", "markets"]
        return list(dict.fromkeys([*requested, *exploration]))
    return ["funding", "capital", "finance", "revenue", "assets", "savings", "local", "off_market", "markets"]


def build_money_search_plan(query: object, *, country: object = "EU", max_lanes: int = MAX_MONEY_QUERY_LANES) -> dict:
    profile = compile_money_profile(query, country=country)
    cleaned = profile["query"]
    if len(cleaned) < 2:
        raise ValueError("Query must contain at least 2 characters")
    max_lanes = max(1, min(MAX_MONEY_QUERY_LANES, int(max_lanes)))

    lanes = [{"query": cleaned, "lane": "exact", "family": None, "source_domain": None}]
    geography = profile["country_name"]
    family_order = _family_order(profile)

    for family in family_order:
        if len(lanes) >= max_lanes:
            break
        terms = FAMILY_EXPANSIONS.get(family)
        if not terms:
            continue
        lanes.append({
            "query": _clean(f"{cleaned} {terms} {geography}"),
            "lane": "mechanism_expansion",
            "family": family,
            "source_domain": None,
        })

    # For focused searches, reserve up to two lanes for authoritative/public
    # sources. Broad "find everything" searches spend their budget on family
    # coverage instead of overfitting to a small domain catalog.
    requested_types = profile.get("requested_types") or []
    requested_families = profile.get("requested_families") or []
    focused = bool(requested_types or (requested_families and len(requested_families) <= 2))
    if focused and len(lanes) < max_lanes:
        sources = sources_for(
            country=profile["country"],
            families=requested_families or family_order[:2],
            types=requested_types,
            limit=2,
        )
        for source in sources:
            if len(lanes) >= max_lanes:
                break
            lanes.append({
                "query": _clean(f"site:{source['domain']} {cleaned}"),
                "lane": "source_probe",
                "family": None,
                "source_domain": source["domain"],
            })

    # Deduplicate query strings while preserving exact query at position zero.
    unique, seen = [], set()
    for lane in lanes:
        key = lane["query"].casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(lane)
    unique = unique[:max_lanes]

    return {
        "version": MONEY_QUERY_PLANNER_VERSION,
        "profile": profile,
        "lanes": unique,
        "queries": [lane["query"] for lane in unique],
        "exact_query_once": True,
        "max_lanes": max_lanes,
        "bounded": True,
        "truth_semantics": "query_expansion_discovers_candidates_not_verified_opportunities",
    }


def money_query_planner_capabilities() -> dict:
    return {
        "version": MONEY_QUERY_PLANNER_VERSION,
        "max_lanes": MAX_MONEY_QUERY_LANES,
        "exact_query_first": True,
        "natural_language_need_expansion": True,
        "source_probe_lanes": True,
        "families": list(FAMILY_EXPANSIONS),
        "truth_semantics": "planner_inference_is_search_strategy_not_eligibility_or_profit_proof",
    }


__all__ = [
    "MAX_MONEY_QUERY_LANES", "MONEY_QUERY_PLANNER_VERSION", "build_money_search_plan",
    "compile_money_profile", "money_query_planner_capabilities",
]
