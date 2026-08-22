"""Universal intelligence router for NameMachine private Global Search.

Opportunity Intelligence remains a separate truth-aware vertical. Other research
modules influence routing, query planning, and retrieval ranking only; they do
not upgrade snippets or preferred hosts into verified facts.
"""
from __future__ import annotations

import re

import requests

import global_search as base_search
from intelligence_modules import (
    MODULE_BY_NAME,
    build_module_search_plan,
    classify_research_module,
    intelligence_module_capabilities,
    source_affinity,
)
from opportunity_search import (
    infer_query_category,
    opportunity_search_capabilities,
    search_global as search_opportunity,
)


AMBIGUOUS_OPPORTUNITY_CATEGORIES = {"funding", "challenge"}
OPPORTUNITY_CONTEXT_PATTERNS = (
    r"\bapply\w*\b", r"\bapplication\w*\b", r"\bopen call\b", r"\bdeadline\b",
    r"\bstartup\w*\b", r"\bsme\b", r"\bprize\w*\b", r"\bgrant\w*\b",
    r"\bopportunit\w*\b", r"\bfind\b", r"\bavailable\b",
    r"\bподат\w*\b", r"\bзаявк\w*\b", r"\bдедлайн\w*\b", r"\bстартап\w*\b",
    r"\bприз(?:и|ів|ом|ами|у|а)?\b", r"\bможливост\w*\b", r"\bзнайд\w*\b", r"\bвідкрит\w*\b",
    r"\bwniosk\w*\b", r"\bnab[oó]r\w*\b", r"\btermin\w*\b", r"\bstartup\w*\b",
    r"\bnagrod\w*\b", r"\bmożliwoś\w*\b", r"\bznajd\w*\b", r"\botwart\w*\b",
)


GENERAL_INTENT_PATTERNS = {
    "current": (
        r"\blatest\b", r"\btoday\b", r"\bcurrent\b", r"\brecent\b", r"\bnews\b",
        r"\bсьогодні\b", r"\bзараз\b", r"\bостанні\w*\b", r"\bновин\w*\b",
        r"\bdzisiaj\b", r"\bteraz\b", r"\bnajnowsz\w*\b", r"\baktualn\w*\b",
    ),
    "comparison": (
        r"\bcompare\b", r"\bversus\b", r"\bvs\.?\b",
        r"\bпорівня\w*\b", r"\bпорівняй\b", r"\bпроти\b",
        r"\bporówn\w*\b", r"\bversus\b",
    ),
    "how_to": (
        r"\bhow to\b", r"\bhow do i\b",
        r"\bяк\s+(?:зробити|знайти|отримати|налаштувати|працює)\b",
        r"\bjak\s+(?:zrobić|znaleźć|uzyskać|ustawić|działa)\b",
    ),
}


# Routing must survive ordinary one-character user typos. This is deliberately
# restricted to high-signal concepts: we never autocorrect arbitrary prose.
TYPO_CANONICAL_TERMS = (
    "бізнес", "business", "biznes",
    "ідеї", "ideas", "idea", "pomysły", "pomysł",
    "грант", "grant", "dotacja",
    "стартап", "startup",
    "інвестиції", "investment", "inwestycje",
    "конкурс", "competition", "prize", "nagroda",
    "можливості", "opportunity", "opportunities", "możliwości",
    "funding", "фінансування", "finansowanie",
)

GENERAL_STOPWORDS = {
    "show", "find", "search", "please", "me", "about", "for", "the", "a", "an",
    "покажи", "знайди", "пошукай", "шукай", "мені", "про", "для", "які", "який", "яка",
    "pokaż", "znajdź", "szukaj", "mi", "dla", "jakie", "jaki", "jaka",
}

SEMANTIC_CONCEPTS = {
    "business": (
        "бізнес", "підприєм", "business", "biznes", "firma", "firmy", "company", "companies",
        "startup", "стартап",
    ),
    "ideas": (
        "іде", "idea", "ideas", "pomysł", "pomys", "concept", "concepts", "trend", "trends",
        "to start", "start a", "launch",
    ),
    "funding": (
        "грант", "grant", "dotac", "funding", "фінанс", "finans", "investment", "інвест", "inwest",
    ),
    "prize": (
        "приз", "конкурс", "prize", "competition", "award", "nagrod", "konkurs",
    ),
    "opportunity": (
        "можливост", "opportunit", "możliwoś", "open call", "nabór", "nabor",
    ),
}


def _one_edit_or_transposition(left: str, right: str) -> bool:
    """Return True when two tokens differ by at most one edit/transposition."""
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        mismatches = [idx for idx, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]
        if len(mismatches) == 1:
            return True
        if len(mismatches) == 2:
            i, j = mismatches
            return j == i + 1 and left[i] == right[j] and left[j] == right[i]
        return False
    short, long = (left, right) if len(left) < len(right) else (right, left)
    i = j = edits = 0
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        j += 1
    return True


def _normalize_query_typos(query: object) -> str:
    """Correct only unambiguous one-edit mistakes in high-signal search words."""
    cleaned = " ".join(str(query or "").split())
    if not cleaned:
        return cleaned

    def replace(match: re.Match) -> str:
        token = match.group(0)
        folded = token.casefold()
        if len(folded) < 4 or folded in TYPO_CANONICAL_TERMS:
            return token
        candidates = [
            canonical for canonical in TYPO_CANONICAL_TERMS
            if abs(len(canonical) - len(folded)) <= 1 and _one_edit_or_transposition(folded, canonical)
        ]
        if len(candidates) != 1:
            return token
        return candidates[0]

    return re.sub(r"[^\W_]+", replace, cleaned, flags=re.UNICODE)


def _semantic_groups(text: object) -> set[str]:
    folded = " ".join(str(text or "").split()).casefold()
    return {
        concept for concept, markers in SEMANTIC_CONCEPTS.items()
        if any(marker in folded for marker in markers)
    }


def _content_tokens(text: object) -> list[str]:
    normalized = _normalize_query_typos(text).casefold()
    words = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
    return [
        word for word in words
        if len(word) >= 3 and not word.isdigit() and word not in GENERAL_STOPWORDS
    ]


def _token_matches_query(token: str, row_text: str) -> bool:
    if token in row_text:
        return True
    if len(token) >= 5:
        stem = token[: max(4, len(token) - 2)]
        if stem in row_text:
            return True
    return False


def _general_result_relevant(title: str, description: str, query: str) -> bool:
    """Fail closed on obvious semantic drift in generic web retrieval."""
    row_text = f"{title} {description}".casefold()
    query_groups = _semantic_groups(query)
    row_groups = _semantic_groups(row_text)
    if query_groups:
        group_hits = len(query_groups & row_groups)
        required = 2 if len(query_groups) >= 2 else 1
        if group_hits >= required:
            return True

    tokens = _content_tokens(query)
    if not tokens:
        return True
    token_hits = sum(1 for token in tokens if _token_matches_query(token, row_text))
    if query_groups:
        # A recognised semantic request must keep at least one semantic anchor;
        # lexical coincidence alone must not admit unrelated translation pages.
        return bool(query_groups & row_groups) and token_hits >= 1
    required_token_hits = 1 if len(tokens) <= 2 else 2
    return token_hits >= required_token_hits


def infer_general_intent(query: object) -> str:
    """Return a coarse, auditable research shape for generic web retrieval."""
    text = _normalize_query_typos(query).casefold()
    scores = {}
    for intent, patterns in GENERAL_INTENT_PATTERNS.items():
        hits = sum(1 for pattern in patterns if re.search(pattern, text, flags=re.I))
        if hits:
            scores[intent] = hits
    if not scores:
        return "general"
    order = list(GENERAL_INTENT_PATTERNS)
    return sorted(scores, key=lambda name: (-scores[name], order.index(name)))[0]


def classify_search_route(query: object, *, category: object = "all") -> dict:
    """Choose the narrowest high-confidence route while keeping fallback neutral."""
    requested = str(category or "all").strip().lower().replace("-", "_")
    normalized_query = _normalize_query_typos(query)
    if requested != "all":
        return {
            "route": "opportunity",
            "reason": "explicit_category",
            "requested_category": requested,
            "routed_category": requested,
            "general_intent": None,
            "module_confidence": 100,
            "module_version": None,
            "normalized_query": normalized_query,
        }

    inferred = infer_query_category(normalized_query)
    text = normalized_query.casefold()
    has_context = any(
        re.search(pattern, text, flags=re.I)
        for pattern in OPPORTUNITY_CONTEXT_PATTERNS
    )
    if inferred != "all" and (
        inferred not in AMBIGUOUS_OPPORTUNITY_CATEGORIES or has_context
    ):
        return {
            "route": "opportunity",
            "reason": "high_confidence_opportunity_intent",
            "requested_category": "all",
            "routed_category": inferred,
            "general_intent": None,
            "module_confidence": 100,
            "module_version": None,
            "normalized_query": normalized_query,
        }

    module = classify_research_module(normalized_query)
    if module["route"] != "general_web":
        return {
            "route": module["route"],
            "reason": module["reason"],
            "requested_category": "all",
            "routed_category": "all",
            "general_intent": infer_general_intent(normalized_query),
            "module_confidence": module["confidence"],
            "module_version": module["module_version"],
            "normalized_query": normalized_query,
        }

    return {
        "route": "general_web",
        "reason": "no_specialized_intent",
        "requested_category": "all",
        "routed_category": "all",
        "general_intent": infer_general_intent(normalized_query),
        "module_confidence": 0,
        "module_version": None,
        "normalized_query": normalized_query,
    }


def _provider_choice() -> tuple[str, dict]:
    providers = base_search._provider_config()
    provider = (
        "brave_web"
        if providers["brave"]
        else "browser_eye_web"
        if providers["browser_eye"]
        else "none"
    )
    return provider, providers


def _run_provider_query(search_query, provider, providers, requester, poster):
    if provider == "brave_web":
        return base_search._brave_query(search_query, providers["brave_key"], requester)
    return base_search._browser_eye_query(
        search_query,
        providers["browser_url"],
        providers["browser_token"],
        poster,
    )


def _general_score(title: str, description: str, query: str, provider_rank: int) -> int:
    text = f"{title} {description}".casefold()
    tokens = base_search._query_tokens(_normalize_query_typos(query))
    token_hits = sum(1 for token in tokens if token in text)
    score = max(0, 55 - min(provider_rank, 35))
    score += min(35, token_hits * 7)
    return max(0, min(100, score))


def _decorate_rows(raw_rows, query, collected, seen, *, route="general_web", query_index=0):
    for provider_rank, raw in enumerate(raw_rows if isinstance(raw_rows, list) else []):
        if not isinstance(raw, dict):
            continue
        title = base_search._clean_text(raw.get("title"), 300)
        description = base_search._clean_text(raw.get("description"), 900)
        url = base_search._clean_text(raw.get("url"), 1000)
        canonical = base_search._canonical_url(url)
        if not title or not canonical or canonical in seen:
            continue
        if route == "general_web" and not _general_result_relevant(title, description, query):
            continue
        seen.add(canonical)
        host = base_search._host(url)
        affinity = source_affinity(route, host) if route != "general_web" else 0
        score = _general_score(title, description, query, provider_rank)
        if affinity:
            score = min(100, score + affinity)
        if query_index == 0:
            score = min(100, score + 3)
        collected.append({
            "title": title,
            "description": description,
            "url": url,
            "host": host,
            "category": "web" if route == "general_web" else route,
            "retrieval_score": score,
            "source_tier": "web",
            "source_name": host,
            "source_country": None,
            "official_source": False,
            "source_affinity": affinity,
            "preferred_source_match": bool(affinity),
            "query_index": query_index,
            "intelligence_route": route,
        })


def _unconfigured_payload(query, *, route, search_plan, general_intent):
    return {
        "query": query,
        "category": "all",
        "country": None,
        "provider": "none",
        "provider_status": "unconfigured",
        "results": [],
        "search_plan": search_plan,
        "intelligence_version": (
            "general-web-v2-semantic-guard" if route == "general_web" else MODULE_BY_NAME[route].version
        ),
        "intelligence_route": route,
        "general_intent": general_intent,
        "truth_note": "No live web provider is configured; no search claims were generated.",
    }


def search_general_web(
    query,
    *,
    requester=requests.get,
    poster=requests.post,
):
    """Run one neutral live-web query with a fail-closed semantic relevance gate."""
    original = base_search._clean_text(query, 1800)
    if len(original) < 2:
        raise ValueError("Query must contain at least 2 characters")
    cleaned = _normalize_query_typos(original)

    provider, providers = _provider_choice()
    general_intent = infer_general_intent(cleaned)
    if provider == "none":
        payload = _unconfigured_payload(
            original,
            route="general_web",
            search_plan=[cleaned],
            general_intent=general_intent,
        )
        payload["normalized_query"] = cleaned
        payload["query_normalized"] = cleaned != original
        return payload

    try:
        status, rows = _run_provider_query(cleaned, provider, providers, requester, poster)
    except requests.RequestException:
        status, rows = "network_error", []
    except (TypeError, ValueError):
        status, rows = "malformed", []

    raw_count = len(rows) if isinstance(rows, list) else 0
    collected = []
    _decorate_rows(rows, cleaned, collected, set(), route="general_web", query_index=0)
    collected.sort(key=lambda row: (-int(row.get("retrieval_score", 0)), str(row.get("title", "")).casefold()))

    return {
        "query": original,
        "normalized_query": cleaned,
        "query_normalized": cleaned != original,
        "category": "all",
        "country": None,
        "provider": provider,
        "provider_status": status,
        "results": collected[:40],
        "search_plan": [cleaned],
        "intelligence_version": "general-web-v2-semantic-guard",
        "intelligence_route": "general_web",
        "general_intent": general_intent,
        "result_guard": {
            "policy": "semantic-relevance-fail-closed-v1",
            "provider_rows": raw_count,
            "accepted_rows": len(collected),
            "rejected_or_deduplicated_rows": max(0, raw_count - len(collected)),
            "irrelevant_results_may_return_zero": True,
        },
        "truth_note": (
            "Web results are retrieval evidence. Generic results are shown only when they "
            "retain semantic anchors from the user query; zero relevant results is preferred "
            "to unrelated filler. Titles and snippets are not independently verified facts."
        ),
    }


def search_module_web(
    query,
    *,
    route,
    requester=requests.get,
    poster=requests.post,
):
    """Run one specialized retrieval module with bounded query expansion."""
    cleaned = base_search._clean_text(query, 1800)
    if len(cleaned) < 2:
        raise ValueError("Query must contain at least 2 characters")
    route = str(route or "").strip().lower()
    if route not in MODULE_BY_NAME:
        raise ValueError("Unknown intelligence module")

    planned = build_module_search_plan(cleaned, route)
    provider, providers = _provider_choice()
    general_intent = infer_general_intent(cleaned)
    if provider == "none":
        return _unconfigured_payload(
            cleaned,
            route=route,
            search_plan=planned,
            general_intent=general_intent,
        )

    collected, seen, statuses, executed = [], set(), [], []
    for query_index, search_query in enumerate(planned):
        executed.append(search_query)
        try:
            status, rows = _run_provider_query(search_query, provider, providers, requester, poster)
        except requests.RequestException:
            status, rows = "network_error", []
        except (TypeError, ValueError):
            status, rows = "malformed", []
        statuses.append(status)
        _decorate_rows(
            rows,
            cleaned,
            collected,
            seen,
            route=route,
            query_index=query_index,
        )
        # Keep the fast path fast. Expansion is only used when the exact query
        # does not already return a healthy result set.
        if status == "complete" and len(collected) >= 10:
            break

    collected.sort(key=lambda row: (-int(row.get("retrieval_score", 0)), int(row.get("query_index", 0)), str(row.get("title", "")).casefold()))
    status = "complete" if collected and "complete" in statuses else (statuses[-1] if statuses else "unknown")
    return {
        "query": cleaned,
        "category": "all",
        "country": None,
        "provider": provider,
        "provider_status": status,
        "results": collected[:40],
        "search_plan": executed,
        "intelligence_version": MODULE_BY_NAME[route].version,
        "intelligence_route": route,
        "general_intent": general_intent,
        "truth_note": (
            f"{route.title()} Intelligence changes retrieval planning and ranking only. "
            "Search snippets and preferred-source matches are evidence, not verified facts."
        ),
    }


def search_universal(
    query,
    *,
    category="all",
    country="EU",
    requester=requests.get,
    poster=requests.post,
    opportunity_searcher=search_opportunity,
    general_searcher=search_general_web,
    module_searcher=search_module_web,
):
    """Route one private-mode query to the narrowest justified intelligence lane."""
    original_query = base_search._clean_text(query, 1800)
    decision = classify_search_route(original_query, category=category)
    effective_query = decision.get("normalized_query") or original_query

    if decision["route"] == "opportunity":
        payload = opportunity_searcher(
            effective_query,
            category=decision["routed_category"],
            country=country,
            requester=requester,
            poster=poster,
        )
        payload["intelligence_route"] = "opportunity"
    elif decision["route"] == "general_web":
        payload = general_searcher(effective_query, requester=requester, poster=poster)
        payload["intelligence_route"] = "general_web"
    else:
        payload = module_searcher(
            effective_query,
            route=decision["route"],
            requester=requester,
            poster=poster,
        )
        payload["intelligence_route"] = decision["route"]

    payload["query"] = original_query
    payload["normalized_query"] = effective_query
    payload["query_normalized"] = effective_query != original_query
    payload["route_reason"] = decision["reason"]
    payload["requested_category"] = decision["requested_category"]
    payload["routed_category"] = decision["routed_category"]
    payload["general_intent"] = decision["general_intent"]
    payload["module_confidence"] = decision["module_confidence"]
    payload["module_version"] = decision["module_version"]
    payload["intent_routed"] = decision["route"] != "general_web"
    return payload


def universal_search_capabilities() -> dict:
    payload = dict(base_search.global_search_capabilities())
    opportunity = opportunity_search_capabilities()
    modules = intelligence_module_capabilities()
    payload.update({
        "intelligence_version": "universal-router-v3-semantic-guard",
        "default_route": "auto",
        "routes": ["general_web", "opportunity", *modules.keys()],
        "natural_language_intent_routing": True,
        "typo_tolerant_high_signal_routing": True,
        "general_web": {
            "neutral_geography": True,
            "forced_opportunity_terms": False,
            "specialized_interpretation": False,
            "semantic_relevance_guard": True,
            "fail_closed_on_irrelevant_filler": True,
        },
        "modules": modules,
        "opportunity": {
            "intelligence_version": opportunity.get("intelligence_version"),
            "priority_scope": opportunity.get("priority_scope", []),
            "priority_categories": opportunity.get("priority_categories", []),
            "deep_source_verification": bool(opportunity.get("deep_source_verification")),
        },
    })
    return payload


__all__ = [
    "classify_search_route",
    "infer_general_intent",
    "search_general_web",
    "search_module_web",
    "search_universal",
    "universal_search_capabilities",
]
