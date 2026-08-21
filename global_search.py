"""Private global/opportunity search layer built on NameMachine's search principles.

This module deliberately distinguishes source provenance from claim verification.
An official-domain hit is an official source observation, not proof that the user
is eligible for a grant, prize, tender, benefit, auction, or other opportunity.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import requests

from brand_collision import BRAVE_SEARCH_URL


ALLOWED_CATEGORIES = {
    "all", "grant", "challenge", "tender", "auction", "funding", "benefit",
    "business_aid", "research", "government", "private",
}

EU_COUNTRIES = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia",
    "CY": "Cyprus", "CZ": "Czechia", "DK": "Denmark", "EE": "Estonia",
    "FI": "Finland", "FR": "France", "DE": "Germany", "GR": "Greece",
    "HU": "Hungary", "IE": "Ireland", "IT": "Italy", "LV": "Latvia",
    "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta", "NL": "Netherlands",
    "PL": "Poland", "PT": "Portugal", "RO": "Romania", "SK": "Slovakia",
    "SI": "Slovenia", "ES": "Spain", "SE": "Sweden",
}

CATEGORY_TERMS = {
    "grant": "grant funding call applications open",
    "challenge": "challenge prize competition open call",
    "tender": "tender procurement contract notice",
    "auction": "auction public sale notice",
    "funding": "funding investment accelerator programme",
    "benefit": "benefit allowance support eligibility",
    "business_aid": "business aid subsidy SME support programme",
    "research": "research call proposal innovation programme",
    "government": "government programme public support call",
    "private": "foundation corporate initiative private funding call",
}

SOURCE_CATALOG = (
    {"domain": "funding-tenders.ec.europa.eu", "kind": "grant", "tier": "official", "country": "EU", "name": "EU Funding & Tenders Portal"},
    {"domain": "ted.europa.eu", "kind": "tender", "tier": "official", "country": "EU", "name": "Tenders Electronic Daily"},
    {"domain": "eic.ec.europa.eu", "kind": "funding", "tier": "official", "country": "EU", "name": "European Innovation Council"},
    {"domain": "cordis.europa.eu", "kind": "research", "tier": "official", "country": "EU", "name": "CORDIS"},
    {"domain": "commission.europa.eu", "kind": "government", "tier": "official", "country": "EU", "name": "European Commission"},
    {"domain": "europa.eu", "kind": "government", "tier": "official", "country": "EU", "name": "European Union"},
    {"domain": "herox.com", "kind": "challenge", "tier": "platform", "country": "INTL", "name": "HeroX"},
    {"domain": "xprize.org", "kind": "challenge", "tier": "platform", "country": "INTL", "name": "XPRIZE"},
    {"domain": "kaggle.com", "kind": "challenge", "tier": "platform", "country": "INTL", "name": "Kaggle"},
    {"domain": "innocentive.com", "kind": "challenge", "tier": "platform", "country": "INTL", "name": "InnoCentive"},
    {"domain": "gov.pl", "kind": "government", "tier": "official", "country": "PL", "name": "Poland Government"},
    {"domain": "funduszeeuropejskie.gov.pl", "kind": "grant", "tier": "official", "country": "PL", "name": "Fundusze Europejskie"},
    {"domain": "parp.gov.pl", "kind": "business_aid", "tier": "official", "country": "PL", "name": "PARP"},
    {"domain": "ncbr.gov.pl", "kind": "research", "tier": "official", "country": "PL", "name": "NCBR"},
)

CLASSIFICATION_PATTERNS = {
    "tender": ("tender", "procurement", "contract notice", "zamówien", "przetarg"),
    "grant": ("grant", "dotac", "dofinansowan", "funding call"),
    "challenge": ("challenge", "prize", "competition", "konkurs"),
    "auction": ("auction", "licytac", "aukcj"),
    "benefit": ("benefit", "allowance", "świadczen", "zasiłek"),
    "business_aid": ("sme support", "business aid", "pomoc dla firm", "przedsiębior"),
    "research": ("research", "horizon", "proposal", "badawcz", "naukow"),
    "funding": ("funding", "accelerator", "investment", "financing"),
}


def _clean_text(value, limit=1200):
    return " ".join(str(value or "").split())[:limit]


def _host(url):
    try:
        return (urlparse(str(url)).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _source_for_host(host):
    host = str(host or "").lower().removeprefix("www.")
    matches = [source for source in SOURCE_CATALOG if host == source["domain"] or host.endswith("." + source["domain"])]
    if not matches:
        return None
    return sorted(matches, key=lambda row: len(row["domain"]), reverse=True)[0]


def normalize_country(value):
    raw = _clean_text(value or "EU", 80)
    if not raw or raw.upper() == "EU":
        return "EU", "European Union"
    upper = raw.upper()
    if upper in EU_COUNTRIES:
        return upper, EU_COUNTRIES[upper]
    for code, name in EU_COUNTRIES.items():
        if raw.casefold() == name.casefold():
            return code, name
    raise ValueError("Unknown EU country")


def normalize_category(value):
    category = _clean_text(value or "all", 40).lower().replace("-", "_")
    aliases = {"grants": "grant", "challenges": "challenge", "tenders": "tender", "auctions": "auction", "benefits": "benefit", "business": "business_aid", "business_support": "business_aid"}
    category = aliases.get(category, category)
    if category not in ALLOWED_CATEGORIES:
        raise ValueError("Unknown global-search category")
    return category


def infer_category(title, description, fallback="all"):
    text = f" {title} {description} ".casefold()
    best = None
    best_hits = 0
    for category, patterns in CLASSIFICATION_PATTERNS.items():
        hits = sum(1 for pattern in patterns if pattern.casefold() in text)
        if hits > best_hits:
            best, best_hits = category, hits
    return best or (fallback if fallback != "all" else "other")


def _source_queries(category, country_code):
    rows = []
    for source in SOURCE_CATALOG:
        if category != "all" and source["kind"] not in {category, "government"}:
            continue
        if country_code != "EU" and source["country"] not in {country_code, "EU", "INTL"}:
            continue
        rows.append(source)
    rows.sort(key=lambda row: (row["tier"] != "official", row["domain"]))
    return rows[:4]


def build_search_plan(query, *, category="all", country="EU"):
    query = _clean_text(query, 1200)
    if len(query) < 2:
        raise ValueError("Query must contain at least 2 characters")
    category = normalize_category(category)
    country_code, country_name = normalize_country(country)
    category_terms = CATEGORY_TERMS.get(category, "")
    geography = "European Union" if country_code == "EU" else country_name
    base = " ".join(part for part in (query, category_terms, geography) if part)
    queries = [base]
    for source in _source_queries(category, country_code):
        queries.append(f"site:{source['domain']} {query} {category_terms}".strip())
    unique = []
    seen = set()
    for item in queries:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item[:1800])
    return {"query": query, "category": category, "country": country_code, "country_name": country_name, "queries": unique[:5]}


def _query_tokens(query):
    return {token.casefold() for token in re.findall(r"[\wÀ-žА-Яа-яІіЇїЄєҐґ]{3,}", str(query), flags=re.UNICODE) if token.casefold() not in {"the", "and", "for", "with", "from", "that", "this"}}


def _score_result(title, description, source, query, provider_rank):
    text = f"{title} {description}".casefold()
    tokens = _query_tokens(query)
    token_hits = sum(1 for token in tokens if token in text)
    score = max(0, 35 - provider_rank)
    score += min(25, token_hits * 5)
    if source:
        score += 25 if source["tier"] == "official" else 12
    if any(term in text for term in ("open", "deadline", "apply", "application", "call", "submission")):
        score += 6
    return max(0, min(100, score))


def _canonical_url(url):
    raw = _clean_text(url, 1000)
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except ValueError:
        return raw
    if not parsed.scheme or not parsed.netloc:
        return raw
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def global_search_capabilities():
    return {
        "provider": "brave_web",
        "provider_configured": bool(os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()),
        "categories": sorted(ALLOWED_CATEGORIES),
        "countries": [{"code": code, "name": name} for code, name in EU_COUNTRIES.items()],
        "eu_wide": True,
        "source_catalog_size": len(SOURCE_CATALOG),
        "source_truth_semantics": "official_source_hit_is_not_eligibility_proof",
        "deduplication": "canonical_url",
        "ranking": "retrieval_relevance_v1",
    }


def search_global(query, *, category="all", country="EU", requester=requests.get):
    plan = build_search_plan(query, category=category, country=country)
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        return {"query": plan["query"], "category": plan["category"], "country": plan["country"], "provider": "brave_web", "provider_status": "unconfigured", "results": [], "search_plan": plan["queries"], "truth_note": "No live web provider is configured; no opportunity claims were generated."}

    headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
    collected = []
    seen = set()
    provider_status = "complete"
    for query_index, search_query in enumerate(plan["queries"]):
        try:
            response = requester(BRAVE_SEARCH_URL, headers=headers, params={"q": search_query, "count": 20, "safesearch": "moderate"}, timeout=10)
        except requests.RequestException:
            provider_status = "partial_network_error" if collected else "network_error"
            continue
        if response.status_code == 429:
            provider_status = "partial_rate_limited" if collected else "rate_limited"
            break
        if response.status_code != 200:
            provider_status = "partial_provider_error" if collected else f"provider_http_{response.status_code}"
            continue
        try:
            payload = response.json() if response.content else {}
        except (TypeError, ValueError):
            provider_status = "partial_malformed" if collected else "malformed"
            continue
        rows = ((payload.get("web") or {}).get("results") or [])[:20]
        for provider_rank, raw in enumerate(rows):
            if not isinstance(raw, dict):
                continue
            title = _clean_text(raw.get("title"), 300)
            description = _clean_text(raw.get("description"), 900)
            url = _clean_text(raw.get("url"), 1000)
            canonical = _canonical_url(url)
            if not title or not canonical or canonical in seen:
                continue
            seen.add(canonical)
            host = _host(url)
            source = _source_for_host(host)
            result_category = infer_category(title, description, plan["category"])
            score = _score_result(title, description, source, plan["query"], query_index * 20 + provider_rank)
            collected.append({"title": title, "description": description, "url": url, "host": host, "category": result_category, "retrieval_score": score, "source_tier": source["tier"] if source else "web", "source_name": source["name"] if source else host, "source_country": source["country"] if source else None, "official_source": bool(source and source["tier"] == "official"), "query_index": query_index})

    collected.sort(key=lambda row: (-int(row.get("official_source", False)), -int(row.get("retrieval_score", 0)), str(row.get("title", "")).casefold()))
    return {"query": plan["query"], "category": plan["category"], "country": plan["country"], "provider": "brave_web", "provider_status": provider_status, "results": collected[:60], "search_plan": plan["queries"], "truth_note": "Results are discovered evidence. Official-source status does not prove eligibility, availability, award amount, or deadline; each item must be checked at its source."}


__all__ = ["ALLOWED_CATEGORIES", "EU_COUNTRIES", "SOURCE_CATALOG", "build_search_plan", "global_search_capabilities", "search_global"]
