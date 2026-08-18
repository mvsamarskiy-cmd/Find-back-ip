import re
from urllib.parse import quote


SUPPORTED_TERRITORIES = ("EU", "PL", "INTL")
DEFAULT_TRADEMARK_CONTEXT = {
    "territories": ["EU", "PL", "INTL"],
    "nice_classes": [],
}


def clean_trademark_context(value):
    """Validate and bound trademark search scope supplied by the browser/API."""
    if value is None:
        return {"territories": list(DEFAULT_TRADEMARK_CONTEXT["territories"]), "nice_classes": []}
    if not isinstance(value, dict):
        raise ValueError("trademark_context must be an object")

    raw_territories = value.get("territories", DEFAULT_TRADEMARK_CONTEXT["territories"])
    if not isinstance(raw_territories, list):
        raise ValueError("Trademark territories must be a list")
    territories = []
    for raw in raw_territories[:3]:
        territory = str(raw).strip().upper()
        if territory not in SUPPORTED_TERRITORIES:
            raise ValueError("Unknown trademark territory")
        if territory not in territories:
            territories.append(territory)
    if not territories:
        raise ValueError("Select at least one trademark territory")

    raw_classes = value.get("nice_classes", [])
    if not isinstance(raw_classes, list):
        raise ValueError("nice_classes must be a list")
    nice_classes = []
    for raw in raw_classes[:45]:
        try:
            value_int = int(raw)
        except (TypeError, ValueError):
            raise ValueError("Nice classes must be integers from 1 to 45")
        if not 1 <= value_int <= 45:
            raise ValueError("Nice classes must be integers from 1 to 45")
        if value_int not in nice_classes:
            nice_classes.append(value_int)

    return {"territories": territories, "nice_classes": sorted(nice_classes)}


def trademark_search_plan(name, context=None):
    """Return official search routes without pretending they are automated evidence.

    WIPO Global Brand Database forbids automated queries/scraping in its public
    terms. EUIPO recommends searching identical and similar signs together with
    goods/services and territory. Until a permitted machine-readable registry
    adapter is configured, risk therefore remains unresolved and the product must
    not label a candidate globally free.
    """
    candidate = " ".join(str(name).split())[:80]
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 .&'-]{1,79}", candidate):
        raise ValueError("Invalid trademark candidate")
    scope = clean_trademark_context(context)
    encoded = quote(candidate)
    return {
        "risk": "unknown",
        "assessment": "manual_search_required",
        "candidate": candidate,
        "territories": scope["territories"],
        "nice_classes": scope["nice_classes"],
        "notice": (
            "No automated registry evidence is available in this release. "
            "Search identical and similar signs in the relevant territories and "
            "goods/services classes. No-hit is not proof that a mark is available."
        ),
        "sources": {
            "euipo_tmview": {
                "label": "EUIPO TMview",
                "url": "https://www.tmdn.org/tmview/",
                "coverage": "EU national offices, EUIPO and participating offices",
                "query": candidate,
            },
            "euipo_esearch": {
                "label": "EUIPO eSearch plus",
                "url": f"https://euipo.europa.eu/eSearch/#basic/1+1+1+1/{encoded}",
                "coverage": "EU trade marks",
                "query": candidate,
            },
            "wipo": {
                "label": "WIPO Global Brand Database",
                "url": "https://branddb.wipo.int/",
                "coverage": "Madrid and participating national/regional collections",
                "query": candidate,
                "automation": "prohibited_on_public_search_service",
            },
            "uprp": {
                "label": "UPRP e-search",
                "url": "https://ewyszukiwarka.pue.uprp.gov.pl/search/simple-search",
                "coverage": "Poland",
                "query": candidate,
            },
        },
        "criteria": [
            "identical_sign",
            "similar_sign",
            "territory",
            "goods_and_services",
            "status_and_priority_date",
        ],
    }


def assess_supplied_matches(name, matches, context=None):
    """Score normalized registry observations supplied by a future adapter/user.

    This function deliberately never fetches registries. It gives a deterministic
    risk classification once trustworthy observations are supplied by a permitted
    adapter. It is the contract the future TMview/registry connector can target.
    """
    plan = trademark_search_plan(name, context)
    if not isinstance(matches, list):
        raise ValueError("matches must be a list")

    exact_active = 0
    similar_active = 0
    relevant_active = 0
    normalized = []
    target = re.sub(r"[^a-z0-9]", "", plan["candidate"].lower())
    requested_classes = set(plan["nice_classes"])

    for raw in matches[:100]:
        if not isinstance(raw, dict):
            continue
        mark = " ".join(str(raw.get("mark", "")).split())[:120]
        if not mark:
            continue
        status = str(raw.get("status", "unknown")).lower()
        active = status in {"active", "registered", "filed", "pending"}
        classes = []
        for item in raw.get("nice_classes", []) if isinstance(raw.get("nice_classes"), list) else []:
            try:
                cls = int(item)
            except (TypeError, ValueError):
                continue
            if 1 <= cls <= 45 and cls not in classes:
                classes.append(cls)
        class_relevant = not requested_classes or bool(requested_classes.intersection(classes))
        normalized_mark = re.sub(r"[^a-z0-9]", "", mark.lower())
        exact = normalized_mark == target
        similarity = raw.get("similarity")
        try:
            similarity = float(similarity) if similarity is not None else None
        except (TypeError, ValueError):
            similarity = None
        similar = bool(similarity is not None and similarity >= 0.75)
        if active and exact:
            exact_active += 1
        if active and similar:
            similar_active += 1
        if active and class_relevant and (exact or similar):
            relevant_active += 1
        normalized.append({
            "mark": mark,
            "status": status,
            "territory": str(raw.get("territory", ""))[:16],
            "nice_classes": classes,
            "exact": exact,
            "similarity": similarity,
            "class_relevant": class_relevant,
        })

    if relevant_active:
        risk = "high" if exact_active else "medium"
    elif exact_active or similar_active:
        risk = "medium"
    elif normalized:
        risk = "low_observed"
    else:
        risk = "unknown"

    plan.update({
        "risk": risk,
        "assessment": "observations_supplied",
        "match_counts": {
            "exact_active": exact_active,
            "similar_active": similar_active,
            "relevant_active": relevant_active,
            "observed": len(normalized),
        },
        "matches": normalized,
    })
    return plan
