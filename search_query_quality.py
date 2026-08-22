"""Query repair and relevance safeguards for private Global Search.

This layer is deliberately conservative: it only repairs one-edit mistakes
against a small intent lexicon, preserves the user's original query for audit,
and refuses to treat provider rank as semantic relevance.
"""
from __future__ import annotations

import re
from typing import Callable

import requests

import global_search as base_search


QUERY_QUALITY_VERSION = "query-quality-v1"
BUSINESS_IDEAS_VERSION = "business-ideas-v1"
MAX_BUSINESS_RESULTS = 20

_INTENT_LEXICON = (
    "бізнес", "бізнесу", "стартап", "ідея", "ідеї", "грант", "гранти",
    "конкурс", "інвестиції", "фінансування",
    "biznes", "biznesu", "pomysł", "pomysły", "startup", "grant", "granty",
    "business", "ideas", "idea", "funding",
)

_ACTION_STOPWORDS = {
    "покажи", "показати", "знайди", "знайти", "мені", "будь", "ласка",
    "дай", "давай", "хочу", "потрібні", "потрібно",
    "show", "find", "give", "tell", "please", "me", "the", "and", "for",
    "with", "from", "this", "that", "about", "some",
    "pokaż", "pokaz", "znajdź", "znajdz", "proszę", "prosze", "mi", "dla",
}

_BUSINESS_IDEA_PATTERNS = (
    r"\bбізнес\w*\b.{0,32}\bіде\w*\b",
    r"\bіде\w*\b.{0,32}\bбізнес\w*\b",
    r"\bbusiness\b.{0,24}\bideas?\b",
    r"\bideas?\b.{0,24}\bbusiness\b",
    r"\bstartup\b.{0,24}\bideas?\b",
    r"\bideas?\b.{0,24}\bstartup\b",
    r"\bbiznes\w*\b.{0,32}\bpomys[łl]\w*\b",
    r"\bpomys[łl]\w*\b.{0,32}\bbiznes\w*\b",
    r"\bwhat business (?:should i|to) start\b",
    r"\bякий бізнес (?:відкрити|почати)\b",
    r"\bjaki biznes (?:otworzy[cć]|zaczą[cć])\b",
)

_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-žА-Яа-яІіЇїЄєҐґ]+", flags=re.UNICODE)


def _one_edit_apart(left: str, right: str) -> bool:
    """Return True only for one substitution/insertion/deletion/transposition."""
    a, b = left.casefold(), right.casefold()
    if a == b:
        return False
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(diffs) == 1:
            return True
        if len(diffs) == 2:
            i, j = diffs
            return j == i + 1 and a[i] == b[j] and a[j] == b[i]
        return False
    short, long = (a, b) if len(a) < len(b) else (b, a)
    i = j = mismatches = 0
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1
            j += 1
            continue
        mismatches += 1
        if mismatches > 1:
            return False
        j += 1
    return True


def repair_search_query(query: object) -> dict:
    """Repair only unambiguous one-edit intent words; never general prose/names."""
    original = " ".join(str(query or "").split()).strip()
    repairs: list[dict] = []

    def replace(match: re.Match) -> str:
        token = match.group(0)
        folded = token.casefold()
        if folded in _INTENT_LEXICON or len(folded) < 5 or folded.isdigit():
            return token
        candidates = [word for word in _INTENT_LEXICON if _one_edit_apart(folded, word)]
        if len(candidates) != 1:
            return token
        repaired = candidates[0]
        repairs.append({"from": token, "to": repaired, "distance": 1})
        return repaired

    routing_query = _TOKEN_RE.sub(replace, original)
    return {
        "version": QUERY_QUALITY_VERSION,
        "original_query": original,
        "routing_query": routing_query,
        "repairs": repairs[:2],
        "changed": bool(repairs),
        "original_preserved": True,
    }


def looks_like_business_idea_query(query: object) -> bool:
    repaired = repair_search_query(query)
    text = repaired["routing_query"].casefold()
    return any(re.search(pattern, text, flags=re.I | re.S) for pattern in _BUSINESS_IDEA_PATTERNS)


def meaningful_query_tokens(query: object) -> set[str]:
    tokens = set()
    for raw in _TOKEN_RE.findall(str(query or "")):
        token = raw.casefold()
        if token in _ACTION_STOPWORDS or token.isdigit() or len(token) < 3:
            continue
        tokens.add(token)
    return tokens


def relevance_hits(title: object, description: object, query: object) -> tuple[int, list[str]]:
    text = f"{title or ''} {description or ''}".casefold()
    matched = sorted(token for token in meaningful_query_tokens(query) if token in text)
    return len(matched), matched


def _normalized_title(value: object) -> str:
    return re.sub(r"[^0-9a-zÀ-žА-Яа-яІіЇїЄєҐґ]+", " ", str(value or "").casefold()).strip()


def apply_general_relevance_guard(payload: dict, *, query: object) -> dict:
    """Drop generic-web rows with zero semantic overlap with the user's query."""
    result = dict(payload or {})
    route = str(result.get("intelligence_route") or "")
    version = str(result.get("intelligence_version") or "")
    if route != "general_web" and version != "general-web-v1":
        return result

    repair = repair_search_query(query)
    relevance_query = repair["routing_query"] or repair["original_query"]
    tokens = meaningful_query_tokens(relevance_query)
    rows = [dict(row) for row in (result.get("results") or []) if isinstance(row, dict)]
    if not tokens:
        return result

    kept = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    rejected = 0
    duplicates = 0
    for row in rows:
        hits, matched = relevance_hits(row.get("title"), row.get("description"), relevance_query)
        if hits < 1:
            rejected += 1
            continue
        canonical = base_search._canonical_url(row.get("url"))
        title_key = _normalized_title(row.get("title"))
        if (canonical and canonical in seen_urls) or (title_key and title_key in seen_titles):
            duplicates += 1
            continue
        if canonical:
            seen_urls.add(canonical)
        if title_key:
            seen_titles.add(title_key)
        row["query_relevance"] = {"hits": hits, "matched_tokens": matched[:8]}
        kept.append(row)

    result["results"] = kept
    result["query_repair"] = repair
    result["relevance_guard"] = {
        "version": QUERY_QUALITY_VERSION,
        "mode": "general_web_zero_overlap_rejection",
        "input_results": len(rows),
        "kept_results": len(kept),
        "zero_overlap_rejected": rejected,
        "duplicates_removed": duplicates,
        "provider_rank_is_not_relevance": True,
    }
    return result


def _provider_choice() -> tuple[str, dict]:
    providers = base_search._provider_config()
    provider = (
        "brave_web" if providers["brave"] else
        "browser_eye_web" if providers["browser_eye"] else
        "none"
    )
    return provider, providers


def _run_provider(search_query: str, provider: str, providers: dict, requester: Callable, poster: Callable):
    if provider == "brave_web":
        return base_search._brave_query(search_query, providers["brave_key"], requester)
    return base_search._browser_eye_query(
        search_query, providers["browser_url"], providers["browser_token"], poster
    )


def _business_plan(query: str, *, country: object) -> tuple[list[str], dict]:
    repair = repair_search_query(query)
    original = repair["original_query"]
    routing = repair["routing_query"]
    plan = [original]
    if routing.casefold() != original.casefold():
        plan.append(routing)
    year_match = re.search(r"\b20\d{2}\b", routing)
    year = year_match.group(0) if year_match else "2026"
    geo_raw = str(country or "EU").strip().upper()
    geography = "Europe" if geo_raw == "EU" else ("Poland" if geo_raw == "PL" else geo_raw)
    english = f"business ideas {year} {geography} market demand trends unmet needs"
    if english.casefold() not in {item.casefold() for item in plan}:
        plan.append(english)
    return plan[:3], repair


def search_business_ideas(
    query: object,
    *,
    country: object = "EU",
    requester: Callable = requests.get,
    poster: Callable = requests.post,
    cancel_checker: Callable[[], bool] | None = None,
) -> dict:
    """Search business-idea evidence with typo repair and strict semantic relevance."""
    original = base_search._clean_text(query, 1800)
    if len(original) < 2:
        raise ValueError("Query must contain at least 2 characters")
    plan, repair = _business_plan(original, country=country)
    provider, providers = _provider_choice()
    if provider == "none":
        return {
            "query": original,
            "category": "all",
            "country": str(country or "EU"),
            "provider": "none",
            "provider_status": "unconfigured",
            "results": [],
            "search_plan": plan,
            "query_repair": repair,
            "intelligence_version": BUSINESS_IDEAS_VERSION,
            "intelligence_route": "business_ideas",
            "intent_routed": True,
            "truth_note": "No live web provider is configured; no business-idea evidence was retrieved.",
        }

    collected: list[dict] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    statuses: list[str] = []
    executed: list[str] = []
    rejected = 0
    duplicates = 0

    for query_index, search_query in enumerate(plan):
        if cancel_checker and cancel_checker():
            break
        executed.append(search_query)
        try:
            status, rows = _run_provider(search_query, provider, providers, requester, poster)
        except requests.RequestException:
            status, rows = "network_error", []
        except (TypeError, ValueError):
            status, rows = "malformed", []
        statuses.append(status)
        for provider_rank, raw in enumerate(rows if isinstance(rows, list) else []):
            if not isinstance(raw, dict):
                continue
            title = base_search._clean_text(raw.get("title"), 300)
            description = base_search._clean_text(raw.get("description"), 900)
            url = base_search._clean_text(raw.get("url"), 1000)
            canonical = base_search._canonical_url(url)
            if not title or not canonical:
                continue
            hits, matched = relevance_hits(title, description, search_query)
            # Business-idea discovery needs at least two meaningful terms. A
            # generic "market" or a year alone must not make a page relevant.
            if hits < 2:
                rejected += 1
                continue
            title_key = _normalized_title(title)
            if canonical in seen_urls or (title_key and title_key in seen_titles):
                duplicates += 1
                continue
            seen_urls.add(canonical)
            if title_key:
                seen_titles.add(title_key)
            score = max(0, min(100, 44 + hits * 12 - min(provider_rank, 20) + (4 if query_index == 0 else 0)))
            host = base_search._host(url)
            collected.append({
                "title": title,
                "description": description,
                "url": url,
                "host": host,
                "category": "business_ideas",
                "retrieval_score": score,
                "source_tier": "web",
                "source_name": host,
                "source_country": None,
                "official_source": False,
                "query_index": query_index,
                "intelligence_route": "business_ideas",
                "query_relevance": {"hits": hits, "matched_tokens": matched[:8]},
                "ui_explanation": {
                    "about": description or f"Джерело про «{title}».",
                    "why": f"У заголовку або фрагменті є {hits} змістові збіги з пошуковою лінією: {', '.join(matched[:5])}.",
                    "value": "Це джерело бізнес-ідей або ринкового сигналу, а не підтверджена готова бізнес-модель.",
                    "uncertainty": "Попит, конкуренція, стартові витрати, маржинальність і придатність саме для користувача ще не підтверджені.",
                },
            })

    collected.sort(key=lambda row: (-int(row.get("retrieval_score", 0)), int(row.get("query_index", 0)), str(row.get("title", "")).casefold()))
    stopped = bool(cancel_checker and cancel_checker())
    provider_status = "stopped" if stopped else (
        "complete" if "complete" in statuses else (statuses[-1] if statuses else "unknown")
    )
    return {
        "query": original,
        "category": "all",
        "country": str(country or "EU"),
        "provider": provider,
        "provider_status": provider_status,
        "results": collected[:MAX_BUSINESS_RESULTS],
        "search_plan": executed,
        "query_repair": repair,
        "relevance_guard": {
            "version": QUERY_QUALITY_VERSION,
            "mode": "business_ideas_min_two_semantic_hits",
            "zero_or_weak_overlap_rejected": rejected,
            "duplicates_removed": duplicates,
            "client_results": min(len(collected), MAX_BUSINESS_RESULTS),
            "provider_rank_is_not_relevance": True,
        },
        "intelligence_version": BUSINESS_IDEAS_VERSION,
        "intelligence_route": "business_ideas",
        "route_reason": "typo_tolerant_business_idea_intent" if repair["changed"] else "business_idea_intent",
        "requested_category": "all",
        "routed_category": "all",
        "general_intent": "business_ideas",
        "module_confidence": 100,
        "module_version": BUSINESS_IDEAS_VERSION,
        "intelligence_routes": ["business_ideas"],
        "multi_intent": False,
        "intent_routed": True,
        "stopped": stopped,
        "truth_note": (
            "Business-idea results are retrieval evidence selected for semantic relevance. "
            "They are not proof of market demand, profitability, low competition or user fit."
        ),
    }


def query_quality_capabilities() -> dict:
    return {
        "version": QUERY_QUALITY_VERSION,
        "one_edit_intent_repair": True,
        "original_query_preserved": True,
        "general_web_zero_overlap_rejection": True,
        "business_ideas": {
            "version": BUSINESS_IDEAS_VERSION,
            "max_provider_queries": 3,
            "max_results": MAX_BUSINESS_RESULTS,
            "minimum_semantic_hits": 2,
            "geography_aware_expansion": True,
        },
    }


__all__ = [
    "BUSINESS_IDEAS_VERSION", "QUERY_QUALITY_VERSION", "apply_general_relevance_guard",
    "looks_like_business_idea_query", "meaningful_query_tokens", "query_quality_capabilities",
    "relevance_hits", "repair_search_query", "search_business_ideas",
]
