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
        name="local",
        version="local-v1",
        threshold=6,
        priority=50,
        patterns=(
            (r"\b(?:near me|nearby|closest|around me|open now|walking distance)\b", 6),
            (r"\b(?:directions|address)\b", 3),
            (r"\b(?:in|near|around)\s+[\wÀ-žА-Яа-яІіЇїЄєҐґ.-]{2,}\b", 3),
            (r"\b(?:(?:restaurant|hotel|cafe|coffee shop|bar|pharmacy|hospital|clinic|dentist|gym|salon|mechanic|parking|museum|park|attraction|airport|station|store|shop|atm|school|police)\w*|banks?)\b", 3),
            (r"\b(?:поруч|біля мене|найближч\w*|відкрит\w* зараз)\b", 6),
            (r"\b(?:адрес\w*|маршрут\w*)\b", 3),
            (r"\b(?:у|в|біля|поруч з)\s+[\wÀ-žА-Яа-яІіЇїЄєҐґ.-]{2,}\b", 3),
            (r"\b(?:ресторан\w*|готел\w*|кафе|кав'ярн\w*|бар\w*|аптек\w*|лікарн\w*|клінік\w*|стоматолог\w*|спортзал\w*|салон\w*|парков\w*|музе\w*|парк\w*|аеропорт\w*|вокзал\w*|магазин\w*|банк\w*|банкомат\w*|школ\w*|поліці\w*)\b", 3),
            (r"\b(?:w pobliżu|blisko mnie|najbliższ\w*|otwarte teraz)\b", 6),
            (r"\b(?:adres\w*|dojazd\w*)\b", 3),
            (r"\b(?:w|koło|obok|blisko)\s+[\wÀ-žА-Яа-яІіЇїЄєҐґ.-]{2,}\b", 3),
            (r"\b(?:restauracj\w*|hotel\w*|kawiarni\w*|bar\w*|aptek\w*|szpital\w*|klinik\w*|dentyst\w*|siłowni\w*|salon\w*|parking\w*|muze\w*|park\w*|lotnisk\w*|dworzec\w*|sklep\w*|bank\w*|bankomat\w*|szkoł\w*|policj\w*)\b", 3),
        ),
        query_suffixes=("address opening hours official website", "reviews directions"),
        preferred_hosts=(
            "tripadvisor.com", "yelp.com", "booking.com", "openstreetmap.org",
            "foursquare.com", "mapquest.com",
        ),
    ),
    IntelligenceModule(
        name="product",
        version="product-v1",
        threshold=6,
        priority=45,
        patterns=(
            (r"\b(?:where to buy|buy|purchase|shopping|for sale|in stock|best price|cheapest|discount|deal|price comparison|compare prices)\b", 6),
            (r"\b(?:price|cost|specs?|specifications?|reviews?)\b", 3),
            (r"\b(?:iphone|ipad|macbook|pixel|galaxy|playstation|xbox|laptop|phone|smartphone|camera|headphones|earbuds|television|tv|monitor|router|vacuum|watch|shoes|sneakers|bike|bicycle)\w*\b", 3),
            (r"\b(?:де купити|купити|продається|в наявності|найдешевш\w*|краща ціна|знижк\w*|акці\w*|порівняти ціни)\b", 6),
            (r"\b(?:ціна|вартіст\w*|характеристик\w*|огляд\w*|відгук\w*)\b", 3),
            (r"\b(?:айфон\w*|макбук\w*|ноутбук\w*|телефон\w*|смартфон\w*|камер\w*|навушник\w*|телевізор\w*|монітор\w*|роутер\w*|пилосос\w*|годинник\w*|взутт\w*|велосипед\w*)\b", 3),
            (r"\b(?:gdzie kupić|kupić|na sprzedaż|dostępn\w*|najtaniej|najlepsza cena|promocj\w*|rabat\w*|porównaj ceny)\b", 6),
            (r"\b(?:cena|koszt|specyfikacj\w*|recenzj\w*|opini\w*)\b", 3),
            (r"\b(?:iphone\w*|macbook\w*|laptop\w*|telefon\w*|smartfon\w*|aparat\w*|słuchawk\w*|telewizor\w*|monitor\w*|router\w*|odkurzacz\w*|zegarek\w*|but\w*|rower\w*)\b", 3),
        ),
        query_suffixes=("price availability specifications reviews", "best deal retailer"),
        preferred_hosts=(
            "ceneo.pl", "idealo.de", "allegro.pl", "amazon.com", "amazon.de",
            "ebay.com", "bestbuy.com", "walmart.com",
        ),
    ),
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
        threshold=3,
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

LOCAL_INFORMATION_GUARD = re.compile(
    r"\b(?:weather|forecast|temperature|погод\w*|температур\w*|прогноз погод\w*|pogod\w*|temperatur\w*|prognoz\w*)\b",
    flags=re.I,
)
PRODUCT_FINANCE_GUARD = re.compile(
    r"\b(?:bitcoin|btc|ethereum|eth|crypto\w*|stock\w*|share price|forex|exchange rate|currency rate|курс валют\w*|акці[яї]\w*|крипт\w*|kurs walut\w*|akcj\w*)\b",
    flags=re.I,
)


def _clean_query(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _module_score(module: IntelligenceModule, text: str) -> int:
    score = 0
    for pattern, weight in module.patterns:
        matches = re.findall(pattern, text, flags=re.I)
        if matches:
            score += weight * min(2, len(matches))
    return score


def _module_is_guarded(module: IntelligenceModule, text: str) -> bool:
    if module.name == "local" and LOCAL_INFORMATION_GUARD.search(text):
        return True
    if module.name == "product" and PRODUCT_FINANCE_GUARD.search(text):
        return True
    return False


def classify_research_module(query: object) -> dict:
    """Choose a high-confidence specialized research module or generic fallback."""
    cleaned = _clean_query(query)
    text = cleaned.casefold()
    candidates = []
    for module in MODULES:
        if _module_is_guarded(module, text):
            continue
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
