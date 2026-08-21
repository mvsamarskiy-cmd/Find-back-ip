"""Specialized research modules for NameMachine Universal Search.

Modules only influence intent routing, query planning, and retrieval ranking.
They do not upgrade search snippets or preferred hosts into verified facts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class IntelligenceModule:
    name: str
    version: str
    threshold: int
    priority: int
    patterns: tuple[tuple[str, int], ...]
    query_suffixes: tuple[str, ...]
    preferred_hosts: tuple[str, ...]


MODULES = (
    IntelligenceModule(
        name="technical",
        version="technical-v1",
        threshold=4,
        priority=40,
        patterns=(
            (r"\b(?:documentation|docs?|api reference|reference docs?|release notes?|changelog|sdk|rfc)\b", 4),
            (r"\b(?:library|package|framework|endpoint|schema|protocol)\b", 2),
            (r"\b(?:документац\w*|реліз\w*|версі\w*|апі|сдк|протокол\w*)\b", 3),
            (r"\b(?:dokumentac\w*|wersj\w*|api|sdk|protok[oó]ł\w*)\b", 3),
        ),
        query_suffixes=("official documentation", "release notes changelog"),
        preferred_hosts=(
            "docs.python.org", "developer.mozilla.org", "github.com", "ietf.org",
            "w3.org", "docs.rs", "pypi.org", "npmjs.com", "readthedocs.io",
            "developer.android.com", "learn.microsoft.com",
        ),
    ),
    IntelligenceModule(
        name="news",
        version="news-v1",
        threshold=4,
        priority=35,
        patterns=(
            (r"\b(?:latest|today|breaking|recent|news|this week|currently)\b", 3),
            (r"\b(?:сьогодні|зараз|новин\w*|останні\w*|актуальн\w*)\b", 3),
            (r"\b(?:dzisiaj|teraz|wiadomoś\w*|najnowsz\w*|aktualn\w*)\b", 3),
            (r"\b(?:what happened|що сталося|co się stało)\b", 3),
        ),
        query_suffixes=("latest developments",),
        preferred_hosts=(
            "reuters.com", "apnews.com", "bbc.com", "ft.com", "bloomberg.com",
            "theguardian.com", "nytimes.com", "wsj.com",
        ),
    ),
    IntelligenceModule(
        name="company",
        version="company-v1",
        threshold=4,
        priority=30,
        patterns=(
            (r"\b(?:company|corporation|business|firm|startup|investor relations)\b", 2),
            (r"\b(?:ceo|cfo|cto|founder|cofounder|revenue|valuation|headquarters|employees)\b", 4),
            (r"\b(?:компані\w*|фірм\w*|стартап\w*|засновник\w*|директор\w*|виручк\w*|оцінк\w*)\b", 2),
            (r"\b(?:firma|sp[oó]łk\w*|startup\w*|założyciel\w*|prezes\w*|przychod\w*|wycen\w*)\b", 2),
        ),
        query_suffixes=("official company investor relations", "company profile leadership"),
        preferred_hosts=(
            "sec.gov", "companieshouse.gov.uk", "opencorporates.com", "crunchbase.com",
        ),
    ),
    IntelligenceModule(
        name="person",
        version="person-v1",
        threshold=4,
        priority=20,
        patterns=(
            (r"\b(?:who is|biography|bio|born|age|career|profile|interview)\b", 3),
            (r"\b(?:хто такий|хто така|біографі\w*|народив\w*|вік|кар'єр\w*|профіль)\b", 3),
            (r"\b(?:kim jest|biografi\w*|urodzi\w*|wiek|karier\w*|profil)\b", 3),
        ),
        query_suffixes=("biography profile",),
        preferred_hosts=("britannica.com", "linkedin.com", "wikipedia.org"),
    ),
)

MODULE_BY_NAME = {module.name: module for module in MODULES}


def _clean_query(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _module_score(module: IntelligenceModule, text: str) -> int:
    return sum(weight for pattern, weight in module.patterns if re.search(pattern, text, flags=re.I))


def classify_research_module(query: object) -> dict:
    """Choose a high-confidence specialized research module or generic fallback."""
    cleaned = _clean_query(query)
    text = cleaned.casefold()
    candidates = []
    for module in MODULES:
        score = _module_score(module, text)
        if score >= module.threshold:
            candidates.append((score, module.priority, module.name))
    if not candidates:
        return {
            "route": "general_web",
            "reason": "no_specialized_research_module",
            "confidence": 0,
            "module_version": None,
        }
    score, _priority, name = sorted(candidates, key=lambda row: (-row[0], -row[1], row[2]))[0]
    module = MODULE_BY_NAME[name]
    return {
        "route": name,
        "reason": "high_confidence_research_module",
        "confidence": min(100, 55 + score * 7),
        "module_version": module.version,
    }


def build_module_search_plan(query: object, route: str) -> list[str]:
    """Build a small, bounded plan. Exact user wording always remains query #1."""
    cleaned = _clean_query(query)
    if len(cleaned) < 2:
        raise ValueError("Query must contain at least 2 characters")
    module = MODULE_BY_NAME.get(str(route or "").strip().lower())
    if not module:
        return [cleaned]
    queries = [cleaned]
    for suffix in module.query_suffixes:
        candidate = f"{cleaned} {suffix}".strip()
        if candidate.casefold() not in {item.casefold() for item in queries}:
            queries.append(candidate[:1800])
        if len(queries) >= 2:
            break
    return queries


def source_affinity(route: str, host: object) -> int:
    """Return ranking-only host affinity. This is never a verification claim."""
    module = MODULE_BY_NAME.get(str(route or "").strip().lower())
    normalized = str(host or "").lower().removeprefix("www.")
    if not module or not normalized:
        return 0
    for preferred in module.preferred_hosts:
        if normalized == preferred or normalized.endswith("." + preferred):
            return 12
    if route == "technical" and (
        normalized.startswith("docs.") or normalized.startswith("developer.")
    ):
        return 8
    return 0


def intelligence_module_capabilities() -> dict:
    return {
        module.name: {
            "version": module.version,
            "query_plan_max": 2,
            "preferred_host_ranking_only": True,
            "truth_semantics": "retrieval_evidence_not_verified_fact",
        }
        for module in MODULES
    }


__all__ = [
    "MODULE_BY_NAME",
    "MODULES",
    "build_module_search_plan",
    "classify_research_module",
    "intelligence_module_capabilities",
    "source_affinity",
]
