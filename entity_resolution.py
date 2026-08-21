"""Conservative deterministic entity resolution for retrieval evidence.

Entity Resolution v1 focuses on product evidence. It separates product-family
identity from exact sellable variants so that price/status comparisons do not
silently merge different storage, colour, size, condition, or model variants.
Ambiguous sources remain ambiguous.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata


ENTITY_RESOLUTION_VERSION = "entity-resolution-v1"
MAX_ENTITY_SOURCES = 40

_GENERIC_TOKENS = {
    "buy", "price", "prices", "best", "cheap", "cheapest", "deal", "sale", "offer",
    "offers", "shop", "store", "online", "official", "latest", "today", "now",
    "available", "availability", "stock", "in", "out", "of", "with", "for", "from",
    "pln", "eur", "usd", "gbp", "zl",
    "kup", "kupic", "cena", "ceny", "najtaniej", "oferta", "sklep", "dostepny",
    "dostepne", "dzisiaj", "teraz", "promocja", "wyprzedaz",
    "купити", "ціна", "ціни", "найдешевше", "пропозиція", "магазин", "наявності",
    "доступний", "доступна", "сьогодні", "зараз", "акція",
}
_MODEL_MODIFIERS = {
    "pro", "max", "plus", "ultra", "mini", "air", "lite", "fe", "se", "edge", "fold",
    "flip", "studio", "sport", "classic", "premium", "elite",
}
_CONDITION_PATTERNS = (
    ("refurbished", re.compile(r"\b(?:refurbished|renewed|reconditioned|odnowion\w*|regenerowan\w*|відновлен\w*)\b", re.I)),
    ("used", re.compile(r"\b(?:used|pre-owned|second hand|używan\w*|uzywan\w*|вживан\w*)\b", re.I)),
    ("new", re.compile(r"\b(?:brand new|factory new|new|nowy|nowa|nowe|новий|нова|нове)\b", re.I)),
)
_STORAGE_RE = re.compile(r"\b(?P<num>\d{1,4})\s*(?P<unit>tb|gb)\b", re.I)
_SIZE_RE = re.compile(r"\b(?P<num>\d{1,3}(?:[.,]\d)?)\s*(?P<unit>inch|inches|\"|cal(?:i|a)?|cm|mm)\b", re.I)
_IDENTIFIER_RE = re.compile(
    r"\b(?P<label>sku|mpn|model(?:\s+number|\s+no\.?|\s+id)?|part(?:\s+number|\s+no\.?)|ean|gtin|upc)\s*[:#-]?\s*"
    r"(?P<value>[A-Z0-9][A-Z0-9._/-]{3,})\b",
    re.I,
)
_MONEY_RE = re.compile(
    r"(?:(?:€|\$|£|PLN|EUR|USD|GBP|zł|zl)\s*\d[\d\s.,]*|"
    r"\d[\d\s.,]*\s*(?:PLN|EUR|USD|GBP|zł|zl|€|\$|£))",
    re.I,
)
_COLOURS = {
    "black": {"black", "czarny", "czarna", "czarne", "чорний", "чорна", "чорне"},
    "white": {"white", "bialy", "biały", "biala", "biała", "biale", "białe", "білий", "біла", "біле"},
    "blue": {"blue", "niebieski", "niebieska", "niebieskie", "синій", "синя", "синє", "блакитний"},
    "green": {"green", "zielony", "zielona", "zielone", "зелений", "зелена", "зелене"},
    "red": {"red", "czerwony", "czerwona", "czerwone", "червоний", "червона", "червоне"},
    "silver": {"silver", "srebrny", "srebrna", "srebrne", "срібний", "срібна"},
    "gold": {"gold", "golden", "zloty", "złoty", "zlota", "złota", "золотий", "золота"},
    "grey": {"grey", "gray", "szary", "szara", "szare", "сірий", "сіра", "сіре"},
    "pink": {"pink", "rozowy", "różowy", "rozowa", "różowa", "рожевий", "рожева"},
    "purple": {"purple", "violet", "fioletowy", "fioletowa", "фіолетовий", "фіолетова"},
    "orange": {"orange", "pomaranczowy", "pomarańczowy", "помаранчевий"},
    "yellow": {"yellow", "zolty", "żółty", "жовтий"},
    "beige": {"beige", "bezowy", "beżowy", "бежевий"},
}


def _clean(value: object, limit: int = 1000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_token(token: str) -> str:
    token = _ascii_fold(token.casefold()).replace("’", "'")
    return re.sub(r"[^a-z0-9а-яіїєґ]+", "", token)


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-zÀ-žА-Яа-яІіЇїЄєҐґ0-9]+(?:[-_/][A-Za-zÀ-žА-Яа-яІіЇїЄєҐґ0-9]+)*", text)
    result = []
    for token in raw:
        normalized = _normalize_token(token)
        if normalized and normalized not in _GENERIC_TOKENS:
            result.append(normalized)
    return result


def _extract_storage(text: str) -> list[str]:
    values = []
    for match in _STORAGE_RE.finditer(text):
        value = f"{int(match.group('num'))}{match.group('unit').upper()}"
        if value not in values:
            values.append(value)
    return values


def _extract_size(text: str) -> list[str]:
    values = []
    for match in _SIZE_RE.finditer(text):
        raw = match.group("num").replace(",", ".")
        unit = match.group("unit").casefold()
        unit = "IN" if unit in {"inch", "inches", '"', "cal", "cali", "cala"} else unit.upper()
        value = f"{raw}{unit}"
        if value not in values:
            values.append(value)
    return values


def _all_colour_alias_tokens() -> set[str]:
    values = set()
    for aliases in _COLOURS.values():
        values.update(_normalize_token(alias) for alias in aliases)
    return values


def _extract_colours(text: str) -> list[str]:
    token_set = {_normalize_token(token) for token in _tokens(text)}
    values = []
    for canonical, aliases in _COLOURS.items():
        if token_set.intersection({_normalize_token(alias) for alias in aliases}):
            values.append(canonical)
    return values


def _extract_condition(text: str) -> str | None:
    for value, pattern in _CONDITION_PATTERNS:
        if pattern.search(text):
            return value
    return None


def _extract_identifiers(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in _IDENTIFIER_RE.finditer(text):
        label = _normalize_token(match.group("label")).replace("number", "")
        value = match.group("value").upper().strip(".-_/ ")
        if not value:
            continue
        if label.startswith("model"):
            key = "model_number"
        elif label.startswith("part"):
            key = "part_number"
        else:
            key = label
        values.setdefault(key, value)
    return values


def _identity_text(text: str) -> str:
    text = _IDENTIFIER_RE.sub(" ", text)
    text = _MONEY_RE.sub(" ", text)
    text = _STORAGE_RE.sub(" ", text)
    text = _SIZE_RE.sub(" ", text)
    return text


def _identity_tokens(title: str, condition: str | None) -> list[str]:
    tokens = _tokens(_identity_text(title))
    remove = _all_colour_alias_tokens()
    if condition:
        remove.add(_normalize_token(condition))
    clean = []
    for token in tokens:
        if token in remove:
            continue
        if token not in clean:
            clean.append(token)
    return clean[:24]


def _model_modifiers(tokens: list[str]) -> list[str]:
    return sorted({token for token in tokens if token in _MODEL_MODIFIERS})


def _distinctive_tokens(tokens: list[str]) -> list[str]:
    distinctive = []
    for token in tokens:
        if token in _MODEL_MODIFIERS:
            distinctive.append(token)
            continue
        has_alpha = bool(re.search(r"[a-zа-яіїєґ]", token))
        has_digit = bool(re.search(r"\d", token))
        if has_alpha and has_digit:
            distinctive.append(token)
        elif token.isdigit() and 2 <= len(token) <= 4:
            distinctive.append(token)
    return sorted(dict.fromkeys(distinctive))


def extract_product_descriptor(source: dict) -> dict:
    """Extract conservative identity and variant attributes from one source record."""
    title = _clean(source.get("title"), 360)
    excerpt = _clean(source.get("excerpt") or source.get("description"), 700)
    text = f"{title} {excerpt}".strip()
    condition = _extract_condition(text)
    identity_tokens = _identity_tokens(title or text, condition)
    return {
        "title": title,
        "source_url": _clean(source.get("url"), 1000),
        "source_host": _clean(source.get("host"), 200).lower(),
        "identity_tokens": identity_tokens,
        "distinctive_tokens": _distinctive_tokens(identity_tokens),
        "model_modifiers": _model_modifiers(identity_tokens),
        "identifiers": _extract_identifiers(text),
        "variant": {
            "storage": _extract_storage(text),
            "colour": _extract_colours(text),
            "size": _extract_size(text),
            "condition": condition,
        },
    }


def _jaccard(left: list[str], right: list[str]) -> float:
    a, b = set(left), set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _identifier_match(left: dict, right: dict) -> tuple[bool, bool]:
    common = set(left).intersection(right)
    if not common:
        return False, False
    matches = any(left[key] == right[key] for key in common)
    conflict = any(left[key] != right[key] for key in common)
    return matches, conflict


def _attribute_conflict(left: list[str], right: list[str]) -> bool:
    return bool(left and right and set(left).isdisjoint(right))


def _variant_conflicts(left: dict, right: dict) -> list[str]:
    conflicts = []
    for key in ("storage", "colour", "size"):
        if _attribute_conflict(left.get(key) or [], right.get(key) or []):
            conflicts.append(key)
    if left.get("condition") and right.get("condition") and left["condition"] != right["condition"]:
        conflicts.append("condition")
    return conflicts


def _shared_variant_evidence(left: dict, right: dict) -> bool:
    for key in ("storage", "colour", "size"):
        lv, rv = left.get(key) or [], right.get(key) or []
        if lv and rv and set(lv).intersection(rv):
            return True
    return bool(left.get("condition") and left.get("condition") == right.get("condition"))


def compare_descriptors(left: dict, right: dict) -> dict:
    """Compare two product descriptors at family and exact-variant levels."""
    id_match, id_conflict = _identifier_match(left.get("identifiers", {}), right.get("identifiers", {}))
    variant_conflicts = _variant_conflicts(left.get("variant", {}), right.get("variant", {}))
    left_modifiers = set(left.get("model_modifiers", []))
    right_modifiers = set(right.get("model_modifiers", []))
    modifier_conflict = bool(left_modifiers != right_modifiers and (left_modifiers or right_modifiers))
    similarity = round(_jaccard(left.get("identity_tokens", []), right.get("identity_tokens", [])), 4)
    distinctive_overlap = sorted(set(left.get("distinctive_tokens", [])).intersection(right.get("distinctive_tokens", [])))

    if id_conflict:
        family_match, basis, confidence = False, "explicit_identifier_conflict", 0
    elif id_match:
        family_match, basis, confidence = True, "explicit_identifier_match", 100
    else:
        family_match = bool(similarity >= 0.72 and distinctive_overlap and not modifier_conflict)
        basis = "token_model_similarity" if family_match else "insufficient_identity_evidence"
        confidence = int(min(96, round(similarity * 100))) if family_match else int(round(similarity * 60))

    exact_variant_match = bool(family_match and not variant_conflicts)
    missing_variant_fields = []
    if exact_variant_match:
        for key in ("storage", "colour", "size", "condition"):
            lv = left.get("variant", {}).get(key)
            rv = right.get("variant", {}).get(key)
            if bool(lv) != bool(rv):
                missing_variant_fields.append(key)
    shared_variant_evidence = _shared_variant_evidence(left.get("variant", {}), right.get("variant", {}))
    exact_variant_safe = bool(
        exact_variant_match
        and (
            id_match
            or (confidence >= 82 and not missing_variant_fields and shared_variant_evidence)
        )
    )

    return {
        "family_match": family_match,
        "family_confidence": confidence,
        "basis": basis,
        "identity_similarity": similarity,
        "distinctive_overlap": distinctive_overlap,
        "modifier_conflict": modifier_conflict,
        "variant_conflicts": variant_conflicts,
        "exact_variant_match": exact_variant_match,
        "exact_variant_safe": exact_variant_safe,
        "missing_variant_fields": missing_variant_fields,
        "shared_variant_evidence": shared_variant_evidence,
    }


def _stable_id(prefix: str, values: list[str]) -> str:
    raw = "|".join(sorted(value for value in values if value))
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


def _canonical_label(descriptors: list[dict]) -> str:
    titles = [item.get("title") for item in descriptors if item.get("title")]
    if not titles:
        return "Unresolved product"
    titles.sort(key=lambda value: (-len(_tokens(_identity_text(value))), len(value), value.casefold()))
    return titles[0][:180]


def _merge_variant(descriptors: list[dict]) -> dict:
    result = {"storage": [], "colour": [], "size": [], "condition": []}
    for descriptor in descriptors:
        variant = descriptor.get("variant", {})
        for key in ("storage", "colour", "size"):
            for value in variant.get(key) or []:
                if value not in result[key]:
                    result[key].append(value)
        condition = variant.get("condition")
        if condition and condition not in result["condition"]:
            result["condition"].append(condition)
    return result


def _family_can_join(candidate: dict, family: list[dict]) -> tuple[bool, int, str]:
    comparisons = [compare_descriptors(candidate, member) for member in family]
    if not comparisons or not all(item["family_match"] for item in comparisons):
        return False, 0, "no_family_match"
    confidence = min(int(item["family_confidence"]) for item in comparisons)
    basis = "explicit_identifier_match" if all(item["basis"] == "explicit_identifier_match" for item in comparisons) else "token_model_similarity"
    return True, confidence, basis


def _variant_can_join(candidate: dict, variant: list[dict]) -> tuple[bool, bool, list[str]]:
    comparisons = [compare_descriptors(candidate, member) for member in variant]
    if not comparisons or not all(item["exact_variant_match"] for item in comparisons):
        conflicts = sorted({field for item in comparisons for field in item["variant_conflicts"]})
        return False, False, conflicts
    safe = all(item["exact_variant_safe"] for item in comparisons)
    missing = sorted({field for item in comparisons for field in item["missing_variant_fields"]})
    return True, safe, missing


def resolve_product_entities(sources: object) -> dict:
    """Resolve product sources into families and conservative variant groups."""
    rows = [row for row in (sources if isinstance(sources, list) else []) if isinstance(row, dict)]
    descriptors = [extract_product_descriptor(row) for row in rows[:MAX_ENTITY_SOURCES]]
    descriptors = [item for item in descriptors if item.get("source_url")]

    families: list[list[dict]] = []
    family_meta: list[dict] = []
    unresolved = []
    for descriptor in descriptors:
        if not descriptor.get("distinctive_tokens") and not descriptor.get("identifiers"):
            unresolved.append({
                "source_url": descriptor["source_url"],
                "source_host": descriptor["source_host"],
                "reason": "insufficient_distinctive_identity",
            })
            continue
        best_index, best_confidence, best_basis = None, -1, None
        for index, family in enumerate(families):
            can_join, confidence, basis = _family_can_join(descriptor, family)
            if can_join and confidence > best_confidence:
                best_index, best_confidence, best_basis = index, confidence, basis
        if best_index is None:
            families.append([descriptor])
            family_meta.append({"confidence": 100, "basis": "seed"})
        else:
            families[best_index].append(descriptor)
            family_meta[best_index]["confidence"] = min(family_meta[best_index]["confidence"], best_confidence)
            family_meta[best_index]["basis"] = best_basis

    family_payloads = []
    variant_payloads = []
    for family_index, family in enumerate(families):
        family_urls = [item["source_url"] for item in family]
        family_id = _stable_id("family", family_urls)
        family_confidence = int(family_meta[family_index]["confidence"])
        if len(family) == 1 and not family[0].get("identifiers"):
            family_confidence = 70
        family_payloads.append({
            "family_id": family_id,
            "canonical_label": _canonical_label(family),
            "source_urls": family_urls,
            "source_hosts": sorted({item["source_host"] for item in family if item.get("source_host")}),
            "identity_tokens": sorted({token for item in family for token in item.get("identity_tokens", [])})[:32],
            "confidence": family_confidence,
            "resolution_basis": family_meta[family_index]["basis"],
        })

        variant_groups: list[list[dict]] = []
        variant_safe_flags: list[bool] = []
        variant_missing: list[set[str]] = []
        for descriptor in family:
            joined = False
            for index, group in enumerate(variant_groups):
                can_join, safe, missing = _variant_can_join(descriptor, group)
                if can_join:
                    group.append(descriptor)
                    variant_safe_flags[index] = variant_safe_flags[index] and safe
                    variant_missing[index].update(missing)
                    joined = True
                    break
            if not joined:
                variant_groups.append([descriptor])
                variant_safe_flags.append(True)
                variant_missing.append(set())

        for index, group in enumerate(variant_groups):
            urls = [item["source_url"] for item in group]
            source_count = len(group)
            comparison_safe = bool(source_count >= 2 and variant_safe_flags[index] and not variant_missing[index])
            variant_payloads.append({
                "entity_id": _stable_id("entity", urls),
                "family_id": family_id,
                "entity_type": "product_variant",
                "canonical_label": _canonical_label(group),
                "source_urls": urls,
                "source_hosts": sorted({item["source_host"] for item in group if item.get("source_host")}),
                "source_count": source_count,
                "variant": _merge_variant(group),
                "comparison_safe": comparison_safe,
                "missing_variant_fields": sorted(variant_missing[index]),
                "resolution_basis": "exact_variant_attributes" if comparison_safe else "family_match_variant_not_fully_proven",
            })

    comparison_groups = [
        {
            "entity_id": item["entity_id"],
            "family_id": item["family_id"],
            "canonical_label": item["canonical_label"],
            "source_urls": item["source_urls"],
            "source_hosts": item["source_hosts"],
            "variant": item["variant"],
        }
        for item in variant_payloads
        if item["comparison_safe"]
    ]

    return {
        "version": ENTITY_RESOLUTION_VERSION,
        "mode": "conservative_product_resolution",
        "family_count": len(family_payloads),
        "entity_count": len(variant_payloads),
        "comparison_safe_group_count": len(comparison_groups),
        "families": family_payloads,
        "entities": variant_payloads,
        "comparison_groups": comparison_groups,
        "unresolved_sources": unresolved,
        "truth_status": {
            "deterministic": True,
            "external_catalog_lookup": False,
            "same_family_is_same_variant": False,
            "missing_variant_attributes_are_assumed_equal": False,
            "comparison_requires_exact_variant_evidence": True,
        },
    }


def entity_resolution_capabilities() -> dict:
    return {
        "version": ENTITY_RESOLUTION_VERSION,
        "deterministic": True,
        "scope": "product_evidence",
        "family_resolution": True,
        "variant_resolution": True,
        "explicit_identifier_support": ["sku", "mpn", "model_number", "part_number", "ean", "gtin", "upc"],
        "variant_attributes": ["storage", "colour", "size", "condition"],
        "external_catalog_lookup": False,
        "comparison_requires_exact_variant_evidence": True,
    }


__all__ = [
    "ENTITY_RESOLUTION_VERSION",
    "compare_descriptors",
    "entity_resolution_capabilities",
    "extract_product_descriptor",
    "resolve_product_entities",
]
