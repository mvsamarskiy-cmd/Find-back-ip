"""Normalization and evidence-aware scoring for private opportunity search.

The module is deliberately conservative. Search snippets and fetched pages are
observations, not legal/eligibility determinations. Unknown facts remain unknown.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from html import unescape
import re
from urllib.parse import urlsplit

import requests


TARGET_CATEGORIES = {"grant", "challenge", "funding", "business_aid", "research"}
VERIFIABLE_HOSTS = {
    "funding-tenders.ec.europa.eu",
    "eic.ec.europa.eu",
    "cordis.europa.eu",
    "commission.europa.eu",
    "europa.eu",
    "funduszeeuropejskie.gov.pl",
    "parp.gov.pl",
    "ncbr.gov.pl",
    "gov.pl",
    "herox.com",
    "xprize.org",
    "kaggle.com",
    "innocentive.com",
}

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6,
    "lipca": 7, "sierpnia": 8, "września": 9, "wrzesnia": 9, "października": 10,
    "pazdziernika": 10, "listopada": 11, "grudnia": 12,
}

DEADLINE_MARKERS = (
    "deadline", "apply by", "applications close", "submission deadline", "closing date",
    "termin składania", "termin skladania", "nabór do", "nabor do", "wnioski do",
    "zgłoszenia do", "zgloszenia do", "applications until", "open until",
)
OPEN_MARKERS = (
    "open call", "applications open", "apply now", "now open", "open for applications",
    "nabór otwarty", "nabor otwarty", "nabór wniosków", "nabor wnioskow", "trwa nabór",
    "trwa nabor", "submit your application",
)
CLOSED_MARKERS = (
    "applications closed", "call closed", "closed for applications", "deadline passed",
    "nabór zakończony", "nabor zakonczony", "zakończono nabór", "zakonczono nabor",
    "konkurs zakończony", "konkurs zakonczony",
)
UPCOMING_MARKERS = (
    "coming soon", "opens on", "upcoming call", "planned call", "nabór planowany",
    "nabor planowany", "wkrótce", "wkrotce",
)

APPLICANT_PATTERNS = {
    "individual": ("individual", "individuals", "natural person", "osoba fizyczna", "osoby fizyczne"),
    "startup": ("startup", "start-up", "startups", "start-ups"),
    "sme": ("sme", "smes", "small and medium", "msp", "mśp", "małe i średnie przedsiębior"),
    "company": ("company", "companies", "business", "enterprise", "przedsiębiorc", "firma", "firmy"),
    "ngo": ("ngo", "non-profit", "nonprofit", "foundation", "association", "fundacja", "stowarzyszenie"),
    "researcher": ("researcher", "researchers", "scientist", "naukowiec", "naukowcy"),
    "research_org": ("research organisation", "research organization", "university", "uczelnia", "jednostka naukowa"),
    "student": ("student", "students", "studentów", "studentow"),
    "public_body": ("public authority", "public body", "municipality", "samorząd", "samorzad", "gmina"),
}

CURRENCY_ALIASES = {
    "€": "EUR", "eur": "EUR", "euro": "EUR",
    "zł": "PLN", "zl": "PLN", "pln": "PLN",
    "$": "USD", "usd": "USD", "dollar": "USD", "dollars": "USD",
}


def _clean(value, limit=8000):
    return " ".join(str(value or "").split())[:limit]


def _plain_html(html, limit=50000):
    raw = str(html or "")[:250000]
    raw = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return _clean(unescape(raw), limit)


def _host(url):
    try:
        return (urlsplit(str(url or "")).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _host_allowed(host):
    return any(host == item or host.endswith("." + item) for item in VERIFIABLE_HOSTS)


def _number_value(raw, suffix=""):
    text = str(raw or "").replace("\u00a0", " ").replace(" ", "")
    if text.count(",") == 1 and "." not in text:
        left, right = text.split(",", 1)
        text = left + "." + right if len(right) <= 2 else left + right
    elif text.count(".") == 1 and "," not in text:
        left, right = text.split(".", 1)
        if len(right) == 3 and len(left) >= 1:
            text = left + right
    else:
        text = text.replace(",", "")
    try:
        value = float(text)
    except ValueError:
        return None
    mult = {"k": 1_000, "thousand": 1_000, "tys": 1_000, "m": 1_000_000, "million": 1_000_000, "mln": 1_000_000}.get(str(suffix or "").lower(), 1)
    return int(round(value * mult))


def extract_amount(text):
    """Return the strongest observed monetary amount/range from text."""
    haystack = _clean(text, 30000)
    pattern = re.compile(
        r"(?P<prefix>€|\$|PLN|EUR|USD|zł|zl)?\s*"
        r"(?P<first>\d{1,3}(?:[\s.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*"
        r"(?P<suffix1>k|m|mln|tys\.?|million|thousand)?\s*"
        r"(?:[-–—]|to|do)\s*"
        r"(?:(?P<prefix2>€|\$|PLN|EUR|USD|zł|zl)\s*)?"
        r"(?P<second>\d{1,3}(?:[\s.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*"
        r"(?P<suffix2>k|m|mln|tys\.?|million|thousand)?\s*"
        r"(?P<currency2>PLN|EUR|USD|euro|zł|zl|dollars?)?",
        re.I,
    )
    single = re.compile(
        r"(?P<prefix>€|\$|PLN|EUR|USD|zł|zl)\s*"
        r"(?P<num>\d{1,3}(?:[\s.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*"
        r"(?P<suffix>k|m|mln|tys\.?|million|thousand)?"
        r"|(?P<num2>\d{1,3}(?:[\s.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*"
        r"(?P<suffix2>k|m|mln|tys\.?|million|thousand)?\s*"
        r"(?P<currency>PLN|EUR|USD|euro|zł|zl|dollars?)",
        re.I,
    )
    candidates = []
    for match in pattern.finditer(haystack):
        currency_raw = match.group("prefix") or match.group("prefix2") or match.group("currency2")
        currency = CURRENCY_ALIASES.get(str(currency_raw or "").lower(), CURRENCY_ALIASES.get(str(currency_raw or ""), None))
        first = _number_value(match.group("first"), (match.group("suffix1") or "").rstrip("."))
        second = _number_value(match.group("second"), (match.group("suffix2") or match.group("suffix1") or "").rstrip("."))
        if currency and first is not None and second is not None:
            low, high = sorted((first, second))
            candidates.append({"currency": currency, "min": low, "max": high, "kind": "range", "evidence": _clean(match.group(0), 140)})
    for match in single.finditer(haystack):
        currency_raw = match.group("prefix") or match.group("currency")
        currency = CURRENCY_ALIASES.get(str(currency_raw or "").lower(), CURRENCY_ALIASES.get(str(currency_raw or ""), None))
        raw_num = match.group("num") or match.group("num2")
        suffix = (match.group("suffix") or match.group("suffix2") or "").rstrip(".")
        value = _number_value(raw_num, suffix)
        if currency and value is not None and value >= 100:
            candidates.append({"currency": currency, "min": None, "max": value, "kind": "observed", "evidence": _clean(match.group(0), 140)})
    if not candidates:
        return None
    candidates.sort(key=lambda row: (int(row.get("max") or 0), row.get("kind") == "range"), reverse=True)
    return candidates[0]


def _parse_date_parts(day, month, year):
    try:
        if isinstance(month, str) and not month.isdigit():
            month = MONTHS.get(month.casefold())
        parsed = date(int(year), int(month), int(day))
        return parsed.isoformat()
    except (TypeError, ValueError):
        return None


def extract_deadline(text):
    haystack = _clean(text, 40000)
    candidates = []
    patterns = [
        re.compile(r"\b(20\d{2})[-/.](0?[1-9]|1[0-2])[-/.]([0-2]?\d|3[01])\b"),
        re.compile(r"\b([0-2]?\d|3[01])[./-](0?[1-9]|1[0-2])[./-](20\d{2})\b"),
        re.compile(r"\b([0-2]?\d|3[01])\s+(" + "|".join(map(re.escape, MONTHS)) + r")\s+(20\d{2})\b", re.I),
        re.compile(r"\b(" + "|".join(map(re.escape, [m for m in MONTHS if m.isascii()])) + r")\s+([0-2]?\d|3[01])(?:st|nd|rd|th)?[,]?\s+(20\d{2})\b", re.I),
    ]
    for index, pattern in enumerate(patterns):
        for match in pattern.finditer(haystack):
            if index == 0:
                iso = _parse_date_parts(match.group(3), match.group(2), match.group(1))
            elif index in {1, 2}:
                iso = _parse_date_parts(match.group(1), match.group(2), match.group(3))
            else:
                iso = _parse_date_parts(match.group(2), match.group(1), match.group(3))
            if not iso:
                continue
            left = max(0, match.start() - 110)
            right = min(len(haystack), match.end() + 110)
            context = haystack[left:right]
            lower = context.casefold()
            marker_hits = sum(marker in lower for marker in DEADLINE_MARKERS)
            score = 0.9 if marker_hits else 0.5
            candidates.append({"date": iso, "confidence": score, "evidence": _clean(context, 240)})
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row["confidence"], row["date"]), reverse=True)
    return candidates[0]


def extract_eligibility(text):
    haystack = _clean(text, 30000).casefold()
    applicants = []
    for key, patterns in APPLICANT_PATTERNS.items():
        if any(pattern.casefold() in haystack for pattern in patterns):
            applicants.append(key)
    explicit_individual_yes = any(term in haystack for term in ("individuals may apply", "open to individuals", "individual applicants", "osoby fizyczne mogą", "osoby fizyczne moga"))
    explicit_individual_no = any(term in haystack for term in ("companies only", "smes only", "only smes", "businesses only", "wyłącznie przedsiębiorc", "wylacznie przedsiebiorc"))
    individual_allowed = True if explicit_individual_yes else False if explicit_individual_no else None
    company_required = True if explicit_individual_no else False if explicit_individual_yes else None
    geography = []
    if any(term in haystack for term in ("poland", "polska", "polish", "w polsce")):
        geography.append("PL")
    if any(term in haystack for term in ("european union", "eu member", "member states", "unia europejska", "państwa członkowskie", "panstwa czlonkowskie")):
        geography.append("EU")
    if any(term in haystack for term in ("worldwide", "global applicants", "open globally", "any country")):
        geography.append("GLOBAL")
    return {
        "applicant_types": applicants,
        "individual_allowed": individual_allowed,
        "company_required": company_required,
        "geography": geography,
    }


def infer_status(text, deadline=None, *, today=None):
    lower = _clean(text, 30000).casefold()
    today = today or datetime.now(timezone.utc).date()
    if deadline and deadline.get("date"):
        try:
            parsed = date.fromisoformat(deadline["date"])
            if parsed < today:
                return {"value": "closed", "confidence": 0.95, "reason": "deadline_passed"}
        except ValueError:
            pass
    if any(marker in lower for marker in CLOSED_MARKERS):
        return {"value": "closed", "confidence": 0.9, "reason": "closed_marker"}
    if any(marker in lower for marker in OPEN_MARKERS):
        return {"value": "open", "confidence": 0.85, "reason": "open_marker"}
    if any(marker in lower for marker in UPCOMING_MARKERS):
        return {"value": "upcoming", "confidence": 0.75, "reason": "upcoming_marker"}
    if deadline and deadline.get("date"):
        try:
            parsed = date.fromisoformat(deadline["date"])
            if parsed >= today:
                return {"value": "open_or_upcoming", "confidence": 0.55, "reason": "future_deadline"}
        except ValueError:
            pass
    return {"value": "unknown", "confidence": 0.0, "reason": "insufficient_evidence"}


def query_profile(query, country="EU"):
    text = _clean(query, 4000).casefold()
    applicants = []
    for key, patterns in APPLICANT_PATTERNS.items():
        if any(pattern.casefold() in text for pattern in patterns):
            applicants.append(key)
    requested_amount = extract_amount(query)
    return {
        "country": str(country or "EU").upper(),
        "applicant_types": applicants,
        "minimum_amount": requested_amount.get("max") if requested_amount else None,
        "minimum_amount_currency": requested_amount.get("currency") if requested_amount else None,
    }


def _fit(row, profile):
    status = (row.get("opportunity") or {}).get("status") or {}
    eligibility = (row.get("opportunity") or {}).get("eligibility") or {}
    amount = (row.get("opportunity") or {}).get("amount")
    verification = (row.get("opportunity") or {}).get("verification") or {}
    retrieval = int(row.get("retrieval_score") or 0)
    score = round(retrieval * 0.35)
    score += 20 if verification.get("source_verified") else 12 if row.get("official_source") else 5
    status_value = status.get("value")
    score += {"open": 15, "open_or_upcoming": 10, "upcoming": 8, "unknown": 4, "closed": 0}.get(status_value, 4)
    blockers = []
    if status_value == "closed":
        blockers.append("closed")
    requested_types = set(profile.get("applicant_types") or [])
    observed_types = set(eligibility.get("applicant_types") or [])
    if requested_types:
        if requested_types & observed_types:
            score += 15
        elif observed_types:
            blockers.append("applicant_type_unmatched")
        else:
            score += 7
    else:
        score += 10
    country = profile.get("country") or "EU"
    geo = set(eligibility.get("geography") or [])
    source_country = row.get("source_country")
    if country == "EU":
        score += 10 if source_country in {"EU", "PL", "INTL"} or geo & {"EU", "GLOBAL"} else 5
    else:
        score += 10 if source_country in {country, "EU", "INTL"} or country in geo or "EU" in geo or "GLOBAL" in geo else 3
    requested_min = profile.get("minimum_amount")
    requested_currency = profile.get("minimum_amount_currency")
    if requested_min:
        if amount and amount.get("currency") == requested_currency:
            if int(amount.get("max") or 0) >= int(requested_min):
                score += 10
            else:
                blockers.append("amount_below_requested")
        else:
            score += 3
    else:
        score += 7
    score = max(0, min(100, score))
    if blockers and "closed" in blockers:
        label = "blocked"
    elif score >= 80:
        label = "high"
    elif score >= 60:
        label = "medium"
    else:
        label = "low"
    return {"score": score, "label": label, "blockers": blockers}


def _verify_one(row, requester=requests.get):
    host = _host(row.get("url"))
    if not _host_allowed(host):
        return {"source_verified": False, "state": "snippet_only", "checked_at": datetime.now(timezone.utc).isoformat(), "page_text": ""}
    try:
        response = requester(
            row.get("url"),
            timeout=5,
            allow_redirects=False,
            headers={"User-Agent": "NameMachine-OpportunityVerifier/1.0", "Accept": "text/html,application/xhtml+xml"},
        )
    except requests.RequestException:
        return {"source_verified": False, "state": "source_unreachable", "checked_at": datetime.now(timezone.utc).isoformat(), "page_text": ""}
    content_type = str(response.headers.get("Content-Type") or "").lower()
    text = _plain_html(response.text if "html" in content_type or not content_type else "", 40000) if response.status_code == 200 else ""
    return {
        "source_verified": response.status_code == 200 and bool(text),
        "state": "source_verified" if response.status_code == 200 and bool(text) else "source_http_error",
        "http_status": response.status_code,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "page_text": text,
    }


def enrich_payload(payload, *, query, country="EU", requester=requests.get, verify_limit=4):
    """Normalize search results and verify a small top set of known sources."""
    result = dict(payload or {})
    rows = [dict(row) for row in (result.get("results") or []) if isinstance(row, dict)]
    profile = query_profile(query, country)

    verify_indexes = [
        index for index, row in enumerate(rows)
        if row.get("category") in TARGET_CATEGORIES and _host_allowed(_host(row.get("url")))
    ][:max(0, int(verify_limit))]
    verified = {}
    if verify_indexes:
        with ThreadPoolExecutor(max_workers=min(4, len(verify_indexes))) as pool:
            futures = {pool.submit(_verify_one, rows[index], requester): index for index in verify_indexes}
            for future in as_completed(futures):
                index = futures[future]
                try:
                    verified[index] = future.result()
                except Exception:
                    verified[index] = {"source_verified": False, "state": "verification_error", "checked_at": datetime.now(timezone.utc).isoformat(), "page_text": ""}

    for index, row in enumerate(rows):
        verification = verified.get(index) or {
            "source_verified": False,
            "state": "snippet_only",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "page_text": "",
        }
        combined = " ".join((str(row.get("title") or ""), str(row.get("description") or ""), verification.get("page_text") or ""))
        amount = extract_amount(combined)
        deadline = extract_deadline(combined)
        eligibility = extract_eligibility(combined)
        status = infer_status(combined, deadline)
        public_verification = {key: value for key, value in verification.items() if key != "page_text"}
        row["opportunity"] = {
            "amount": amount,
            "deadline": deadline,
            "status": status,
            "eligibility": eligibility,
            "verification": public_verification,
        }
        row["fit"] = _fit(row, profile)
        row["normalized"] = True
    rows.sort(key=lambda row: (-int((row.get("fit") or {}).get("score") or 0), -int(row.get("official_source") or False), -int(row.get("retrieval_score") or 0)))
    result["results"] = rows
    result["query_profile"] = profile
    result["intelligence_version"] = "opportunity-v1"
    result["truth_note"] = "Opportunity fields are extracted from search/source evidence and can remain unknown. Source verification confirms the page was observed, not that the user is legally eligible or guaranteed funding."
    return result


__all__ = [
    "TARGET_CATEGORIES", "VERIFIABLE_HOSTS", "enrich_payload", "extract_amount",
    "extract_deadline", "extract_eligibility", "infer_status", "query_profile",
]
