"""Final Money-result quality gate for user-facing private search payloads.

This layer is intentionally conservative. A UI-selected category is a
requirement for a candidate, never evidence that an arbitrary web result belongs
to that category. The gate also bounds the client payload and attaches a compact,
truthful explanation for cards without inventing facts missing from the source.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from money_taxonomy import FAMILIES, TYPE_BY_ID, infer_money_types


MONEY_RESULT_QUALITY_VERSION = "money-result-quality-v1"
MAX_CLIENT_RESULTS = 60

LEGACY_SCOPE = {
    "tender": "procurement",
    "auction": "public_auction",
    "benefit": "savings",
    "business_aid": "funding",
    "research": "research_funding",
    "government": "funding",
    "private": "capital",
}


def _clean(value: object, limit: int = 1600) -> str:
    return " ".join(str(value or "").split())[:limit]


def _canonical_url(value: object) -> str:
    raw = _clean(value, 2400)
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw.casefold()
    host = (parsed.hostname or "").casefold()
    if not host:
        return raw.casefold()
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(((parsed.scheme or "https").casefold(), host, path, "", ""))


def _normalized_title(value: object) -> str:
    text = _clean(value, 500).casefold()
    return re.sub(r"[^0-9a-ząćęłńóśźżа-яіїєґ]+", " ", text, flags=re.I).strip()


def _raw_evidence_text(row: dict) -> str:
    # Deliberately use retrieval text, not normalized/fallback category labels.
    # This prevents the selected category itself from becoming self-evidence.
    return _clean(f"{row.get('title') or ''} {row.get('description') or ''}", 5000)


def _observed_types(row: dict) -> list[str]:
    return infer_money_types(_raw_evidence_text(row), limit=12)


def _scope(category: object) -> tuple[str | None, str | None]:
    raw = str(category or "all").strip().casefold().replace("-", "_") or "all"
    scoped = LEGACY_SCOPE.get(raw, raw)
    if scoped == "all":
        return None, None
    if scoped in TYPE_BY_ID:
        return "type", scoped
    if scoped in FAMILIES:
        return "family", scoped
    return None, None


def _matches_scope(row: dict, kind: str | None, value: str | None) -> bool:
    if not kind or not value:
        return True
    observed = _observed_types(row)
    if kind == "type":
        return value in observed
    return any(TYPE_BY_ID[item].family == value for item in observed if item in TYPE_BY_ID)


def _amount_text(record: dict) -> str:
    amount = record.get("amount") or {}
    display = _clean(amount.get("display"), 160)
    if display:
        return display
    currency = _clean(amount.get("currency"), 12)
    minimum, maximum = amount.get("min"), amount.get("max")
    if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)):
        return f"{minimum:g}–{maximum:g} {currency}".strip()
    if isinstance(maximum, (int, float)):
        return f"до {maximum:g} {currency}".strip()
    if isinstance(minimum, (int, float)):
        return f"від {minimum:g} {currency}".strip()
    return ""


def _explanation(row: dict, *, requested_category: object, kind: str | None, value: str | None) -> dict:
    record = row.get("money_record") if isinstance(row.get("money_record"), dict) else {}
    snippet = _clean(row.get("description"), 360)
    title = _clean(row.get("title"), 260)
    about = snippet or (f"Джерело має заголовок «{title}». Детальніший зміст у пошуковому фрагменті не отримано." if title else "Зміст джерела ще не витягнуто.")

    observed = _observed_types(row)
    if kind == "type" and value:
        why = f"У тексті джерела знайдено ознаки вибраного типу «{value}»."
    elif kind == "family" and value:
        matched = [item for item in observed if item in TYPE_BY_ID and TYPE_BY_ID[item].family == value]
        why = f"У тексті джерела знайдено ознаки напряму «{value}»" + (f": {', '.join(matched[:4])}." if matched else ".")
    elif observed:
        why = f"У тексті джерела розпізнано типи можливості: {', '.join(observed[:4])}."
    else:
        why = "Категорія можливості не підтверджена текстом джерела; результат показано лише як загальний пошуковий кандидат."

    amount = _amount_text(record)
    if amount:
        value_text = f"Витягнута сума або діапазон: {amount}."
    else:
        value_text = "Конкретну суму або матеріальну вигоду з цього фрагмента не підтверджено."

    unknown = []
    if not record.get("source_observed"):
        unknown.append("першоджерело ще не переглянуте системою")
    if not record.get("current_call_verified"):
        unknown.append("поточна доступність не підтверджена")
    eligibility = _clean(record.get("eligibility_state"), 80)
    if not eligibility or eligibility == "unknown":
        unknown.append("відповідність користувачу не визначена")
    uncertainty = "; ".join(unknown) + "." if unknown else "Ключові поля мають пряме джерельне спостереження; все одно перевір умови перед дією."

    return {
        "about": about,
        "why": why,
        "value": value_text,
        "uncertainty": uncertainty,
        "observed_types": observed,
        "requested_category": str(requested_category or "all"),
    }


def apply_money_result_quality(payload: dict, *, category: object = "all", max_results: int = MAX_CLIENT_RESULTS) -> dict:
    result = dict(payload or {})
    rows = [dict(row) for row in (result.get("results") or []) if isinstance(row, dict)]
    before = len(rows)
    kind, value = _scope(category)

    scoped = [row for row in rows if _matches_scope(row, kind, value)]
    scoped_out = before - len(scoped)

    deduped = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    seen_records: set[str] = set()
    duplicate_count = 0
    for row in scoped:
        record = row.get("money_record") if isinstance(row.get("money_record"), dict) else {}
        record_id = _clean(record.get("opportunity_id"), 160)
        url_key = _canonical_url(row.get("url"))
        title_key = _normalized_title(row.get("title"))
        duplicate = bool(
            (record_id and record_id in seen_records)
            or (url_key and url_key in seen_urls)
            or (title_key and title_key in seen_titles)
        )
        if duplicate:
            duplicate_count += 1
            continue
        if record_id:
            seen_records.add(record_id)
        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        row["ui_explanation"] = _explanation(row, requested_category=category, kind=kind, value=value)
        deduped.append(row)

    limit = max(1, min(MAX_CLIENT_RESULTS, int(max_results or MAX_CLIENT_RESULTS)))
    kept = deduped[:limit]
    truncated = max(0, len(deduped) - len(kept))

    kept_record_ids = {
        _clean((row.get("money_record") or {}).get("opportunity_id"), 160)
        for row in kept if isinstance(row.get("money_record"), dict)
    }
    kept_record_ids.discard("")
    # Some internal callers legitimately provide graph-ready `money_records`
    # without retrieval `results`. In that shape there is nothing to scope or
    # deduplicate at the UI-row layer, so preserve those records for graph
    # construction. When retrieval rows did exist, prune records to the rows that
    # survived the final quality gate so rejected noise cannot leak into the graph.
    if before > 0 and isinstance(result.get("money_records"), list):
        result["money_records"] = [
            record for record in result["money_records"]
            if isinstance(record, dict) and _clean(record.get("opportunity_id"), 160) in kept_record_ids
        ]

    result["results"] = kept
    result["result_quality"] = {
        "version": MONEY_RESULT_QUALITY_VERSION,
        "requested_category": str(category or "all"),
        "scope_kind": kind,
        "scope_value": value,
        "input_results": before,
        "scope_rejected": scoped_out,
        "duplicates_removed": duplicate_count,
        "client_results": len(kept),
        "truncated": truncated,
        "max_client_results": limit,
        "selected_category_is_requirement_not_evidence": True,
    }
    return result


def money_result_quality_capabilities() -> dict:
    return {
        "version": MONEY_RESULT_QUALITY_VERSION,
        "strict_selected_scope": True,
        "selected_category_is_requirement_not_evidence": True,
        "canonical_url_dedupe": True,
        "normalized_title_dedupe": True,
        "max_client_results": MAX_CLIENT_RESULTS,
        "human_explanation": True,
    }


__all__ = [
    "MAX_CLIENT_RESULTS", "MONEY_RESULT_QUALITY_VERSION", "apply_money_result_quality",
    "money_result_quality_capabilities",
]
