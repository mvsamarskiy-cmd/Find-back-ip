"""Conservative brand-collision screening for NameMachine.

This module deliberately separates *observed collisions* from legal clearance.
A search-engine no-hit, a company-registry no-hit, or a trademark no-hit is never
promoted to "brand free". Providers may be unconfigured; those layers remain
explicitly unresolved instead of silently becoming green.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import os
import re
from urllib.parse import quote, urlparse

import requests

from trademark_risk import clean_trademark_context, trademark_search_plan


BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
COMPANIES_HOUSE_SEARCH_URL = "https://api.company-information.service.gov.uk/search/companies"
ALLOWED_COMPANY_MARKETS = ("PL", "GB", "INTL")
DEFAULT_COMPANY_MARKETS = ("PL", "GB", "INTL")

_COMMERCIAL_TERMS = {
    "company", "official", "brand", "product", "software", "platform", "app",
    "store", "shop", "agency", "studio", "limited", "ltd", "inc", "llc",
    "plc", "sp z oo", "sp zoo", "s a", "sa", "gmbh", "sarl", "sas",
}
_COMPANY_SUFFIX_RE = re.compile(
    r"\b(?:limited|ltd|plc|llp|llc|inc|incorporated|corp|corporation|company|co|"
    r"gmbh|sarl|sas|sp\s*z\s*o\s*o|sp\s*zoo|s\s*a|sa)\b",
    re.IGNORECASE,
)


def _clean_text(value, limit=500):
    return " ".join(str(value or "").split())[:limit]


def _normalize(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _company_core(value):
    text = _COMPANY_SUFFIX_RE.sub(" ", str(value or ""))
    return _normalize(text)


def _clean_name(value):
    name = _clean_text(value, 80)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 .&'-]{1,79}", name):
        raise ValueError("Invalid brand candidate")
    return name


def clean_company_markets(value):
    if value is None:
        return list(DEFAULT_COMPANY_MARKETS)
    if not isinstance(value, list):
        raise ValueError("company_markets must be a list")
    markets = []
    for raw in value[:3]:
        market = str(raw or "").strip().upper()
        if market not in ALLOWED_COMPANY_MARKETS:
            raise ValueError("Unknown company market")
        if market not in markets:
            markets.append(market)
    if not markets:
        raise ValueError("Select at least one company market")
    return markets


def _provider_failure(provider, reason, *, configured=True, status="unknown"):
    return {
        "provider": provider,
        "configured": configured,
        "status": status,
        "signal": "unknown",
        "reason": reason,
        "results": [],
    }


def _web_result(raw, target):
    title = _clean_text(raw.get("title"), 240)
    description = _clean_text(raw.get("description"), 600)
    url = _clean_text(raw.get("url"), 500)
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    host_label = host.split(".")[0] if host else ""
    target_norm = _normalize(target)
    title_norm = _normalize(title)
    exact_title = bool(target_norm and title_norm == target_norm)
    exact_domain = bool(target_norm and _normalize(host_label) == target_norm)
    combined = f" {title.lower()} {description.lower()} "
    commercial = exact_domain or any(term in combined for term in _COMMERCIAL_TERMS)
    exact_mention = bool(target_norm and target_norm in title_norm)
    return {
        "title": title,
        "url": url,
        "host": host,
        "description": description,
        "exact_title": exact_title,
        "exact_domain": exact_domain,
        "exact_mention": exact_mention,
        "commercial_signal": commercial,
    }


def brave_web_collision(name, *, requester=requests.get):
    candidate = _clean_name(name)
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        result = _provider_failure(
            "brave_web",
            "BRAVE_SEARCH_API_KEY is not configured",
            configured=False,
        )
        result["manual_search"] = f"https://www.google.com/search?q={quote(candidate)}"
        return result

    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }
    queries = [
        f'"{candidate}"',
        f'"{candidate}" company brand product app',
    ]
    seen = set()
    rows = []
    try:
        for query in queries:
            response = requester(
                BRAVE_SEARCH_URL,
                headers=headers,
                params={"q": query, "count": 10, "safesearch": "moderate"},
                timeout=8,
            )
            if response.status_code == 429:
                return _provider_failure("brave_web", "provider rate limited", status="rate_limited")
            if response.status_code != 200:
                return _provider_failure("brave_web", f"provider HTTP {response.status_code}")
            payload = response.json() if response.content else {}
            for raw in ((payload.get("web") or {}).get("results") or [])[:10]:
                if not isinstance(raw, dict):
                    continue
                item = _web_result(raw, candidate)
                key = item["url"].lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                rows.append(item)
                if len(rows) >= 20:
                    break
    except requests.RequestException:
        return _provider_failure("brave_web", "provider network error")
    except (TypeError, ValueError):
        return _provider_failure("brave_web", "provider returned malformed data")

    exact_domain = sum(1 for row in rows if row["exact_domain"])
    exact_title = sum(1 for row in rows if row["exact_title"])
    exact_mentions = sum(1 for row in rows if row["exact_mention"])
    commercial = sum(1 for row in rows if row["commercial_signal"] and row["exact_mention"])

    if exact_domain or (exact_title and commercial):
        signal = "high"
    elif commercial >= 2 or exact_mentions >= 3:
        signal = "medium"
    elif rows:
        signal = "low_observed"
    else:
        signal = "none_observed"

    return {
        "provider": "brave_web",
        "configured": True,
        "status": "complete",
        "signal": signal,
        "reason": "Observed public web presence; no-hit is not proof of availability.",
        "counts": {
            "observed": len(rows),
            "exact_domain": exact_domain,
            "exact_title": exact_title,
            "exact_mentions": exact_mentions,
            "commercial_exact_mentions": commercial,
        },
        "results": rows[:12],
        "manual_search": f"https://www.google.com/search?q={quote(candidate)}",
    }


def companies_house_collision(name, *, requester=requests.get):
    candidate = _clean_name(name)
    api_key = os.environ.get("COMPANIES_HOUSE_API_KEY", "").strip()
    if not api_key:
        return _provider_failure(
            "companies_house",
            "COMPANIES_HOUSE_API_KEY is not configured",
            configured=False,
        )

    try:
        response = requester(
            COMPANIES_HOUSE_SEARCH_URL,
            auth=(api_key, ""),
            params={"q": candidate, "items_per_page": 20},
            timeout=8,
            headers={"Accept": "application/json"},
        )
        if response.status_code == 429:
            return _provider_failure("companies_house", "provider rate limited", status="rate_limited")
        if response.status_code != 200:
            return _provider_failure("companies_house", f"provider HTTP {response.status_code}")
        payload = response.json() if response.content else {}
    except requests.RequestException:
        return _provider_failure("companies_house", "provider network error")
    except (TypeError, ValueError):
        return _provider_failure("companies_house", "provider returned malformed data")

    target = _company_core(candidate)
    rows = []
    exact_active = 0
    similar_active = 0
    exact_inactive = 0
    for raw in (payload.get("items") or [])[:20]:
        if not isinstance(raw, dict):
            continue
        title = _clean_text(raw.get("title"), 160)
        if not title:
            continue
        core = _company_core(title)
        similarity = SequenceMatcher(None, target, core).ratio() if target and core else 0.0
        exact = core == target
        similar = similarity >= 0.82
        status = _clean_text(raw.get("company_status"), 60).lower() or "unknown"
        active = status not in {
            "dissolved", "converted-closed", "closed", "removed", "liquidation",
        }
        if exact and active:
            exact_active += 1
        elif exact:
            exact_inactive += 1
        if similar and active and not exact:
            similar_active += 1
        rows.append({
            "name": title,
            "company_number": _clean_text(raw.get("company_number"), 40),
            "status": status,
            "active": active,
            "exact": exact,
            "similarity": round(similarity, 4),
            "address": _clean_text(raw.get("address_snippet"), 240),
            "created": _clean_text(raw.get("date_of_creation"), 40),
            "url": (
                "https://find-and-update.company-information.service.gov.uk/company/"
                + quote(_clean_text(raw.get("company_number"), 40))
            ) if raw.get("company_number") else "",
        })

    if exact_active:
        signal = "high"
    elif exact_inactive or similar_active:
        signal = "medium"
    elif rows:
        signal = "low_observed"
    else:
        signal = "none_observed"

    return {
        "provider": "companies_house",
        "coverage": "United Kingdom",
        "configured": True,
        "status": "complete",
        "signal": signal,
        "reason": "UK company-register observations only; this is not global company clearance.",
        "counts": {
            "observed": len(rows),
            "exact_active": exact_active,
            "exact_inactive": exact_inactive,
            "similar_active": similar_active,
        },
        "results": rows[:12],
    }


def manual_company_sources(candidate, company_markets):
    sources = []
    if "PL" in company_markets:
        sources.append({
            "market": "PL",
            "label": "KRS — wyszukiwarka podmiotów",
            "url": "https://wyszukiwarka-krs.ms.gov.pl/",
            "automation": "manual_search_required",
        })
    if "INTL" in company_markets:
        sources.append({
            "market": "INTL",
            "label": "GLEIF LEI Search",
            "url": f"https://lei.bloomberg.com/search?searchTerm={quote(candidate)}",
            "automation": "supplemental_manual_search",
            "notice": "LEI coverage is not a complete registry of all companies worldwide.",
        })
    return sources


def build_brand_collision(name, context=None, *, requester=requests.get):
    candidate = _clean_name(name)
    context = context if isinstance(context, dict) else {}
    company_markets = clean_company_markets(context.get("company_markets"))
    trademark_context = clean_trademark_context(context.get("trademark_context"))

    web = brave_web_collision(candidate, requester=requester)
    companies = companies_house_collision(candidate, requester=requester) if "GB" in company_markets else {
        "provider": "companies_house",
        "coverage": "United Kingdom",
        "configured": bool(os.environ.get("COMPANIES_HOUSE_API_KEY")),
        "status": "skipped",
        "signal": "unknown",
        "reason": "GB was not selected in company_markets",
        "results": [],
    }
    trademarks = trademark_search_plan(candidate, trademark_context)

    observed = [web.get("signal"), companies.get("signal")]
    severity = {"unknown": -1, "none_observed": 0, "low_observed": 1, "medium": 2, "high": 3}
    known = [value for value in observed if value in severity and value != "unknown"]
    collision_signal = max(known, key=lambda value: severity[value]) if known else "unknown"

    if collision_signal == "high":
        recommendation = "avoid_or_investigate"
    elif collision_signal == "medium":
        recommendation = "manual_review_required"
    elif collision_signal in {"low_observed", "none_observed"}:
        recommendation = "continue_due_diligence"
    else:
        recommendation = "configure_or_run_sources"

    return {
        "candidate": candidate,
        "collision_signal": collision_signal,
        "clearance_complete": False,
        "legal_clearance": False,
        "recommendation": recommendation,
        "notice": (
            "This is collision screening, not a legal conclusion that a brand is free. "
            "Unconfigured or no-hit sources remain unresolved."
        ),
        "coverage": {
            "web_automated": web.get("status") == "complete",
            "companies_uk_automated": companies.get("status") == "complete",
            "companies_requested_markets": company_markets,
            "trademarks_automated": False,
            "trademark_territories": trademark_context["territories"],
            "nice_classes": trademark_context["nice_classes"],
        },
        "web": web,
        "companies": {
            "uk": companies,
            "manual_sources": manual_company_sources(candidate, company_markets),
        },
        "trademarks": trademarks,
    }


def brand_collision_diagnostics():
    return {
        "enabled": True,
        "semantic": "collision_screening_not_brand_availability",
        "web": {
            "provider": "brave_web",
            "configured": bool(os.environ.get("BRAVE_SEARCH_API_KEY")),
        },
        "company_registries": {
            "companies_house_gb": bool(os.environ.get("COMPANIES_HOUSE_API_KEY")),
            "poland_krs": "manual_search_v1",
            "global_registry": "not_claimed",
        },
        "trademarks": {
            "automated_registry": False,
            "risk_contract": True,
            "manual_sources": ["EUIPO TMview", "EUIPO eSearch", "WIPO GBD", "UPRP"],
        },
        "can_return_brand_free": False,
    }


__all__ = [
    "build_brand_collision",
    "brand_collision_diagnostics",
    "brave_web_collision",
    "clean_company_markets",
    "companies_house_collision",
]
