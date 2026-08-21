"""Source Expansion registry and bounded source-class planner for Money v2.4.

Registry membership is a discovery/trust hint only. A source being public or
official does not prove that an individual opportunity is open, current,
authentic, eligible or profitable.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


SOURCE_EXPANSION_VERSION = "money-source-expansion-v2.4"
MAX_SOURCE_EXPANSION_LANES = 5


@dataclass(frozen=True)
class ExpandedSource:
    domain: str
    name: str
    tier: str
    country: str
    source_class: str
    families: tuple[str, ...]
    types: tuple[str, ...]
    evidence_note: str


# High-value sources verified as current during the v2.4 build. Existing v2
# catalog sources remain available through money_sources; this list is additive.
EXPANDED_SOURCES = (
    ExpandedSource(
        "arp.pl", "Agencja Rozwoju Przemysłu", "public", "PL", "public_finance",
        ("finance", "funding", "assets"),
        ("preferential_loan", "equipment_financing", "leasing", "guarantee"),
        "Public development agency pages currently expose investment, working-capital, grant-bridge and equipment financing products.",
    ),
    ExpandedSource(
        "paih.gov.pl", "Polska Agencja Inwestycji i Handlu", "official", "PL", "export_trade",
        ("revenue", "savings", "markets", "off_market"),
        ("export_support", "supplier_demand", "import_export_gap", "corporate_open_call"),
        "Official PAIH pages currently expose exporter/investor support, partner discovery and market-expansion services.",
    ),
    ExpandedSource(
        "een.ec.europa.eu", "Enterprise Europe Network", "official", "EU", "eu_partnering",
        ("revenue", "markets", "off_market", "funding"),
        ("supplier_demand", "subcontract", "import_export_gap", "corporate_open_call", "research_funding"),
        "European Commission-backed network with a live database of business, technology and R&D partnering opportunities.",
    ),
    ExpandedSource(
        "euraxess.ec.europa.eu", "EURAXESS", "official", "EU", "research_jobs_funding",
        ("funding", "revenue"),
        ("research_funding", "fellowship", "scholarship", "job_contract", "paid_open_call"),
        "European research portal currently exposes jobs, hosting and national/regional funding opportunities.",
    ),
    ExpandedSource(
        "eismea.ec.europa.eu", "EISMEA", "official", "EU", "eu_sme_agency",
        ("funding", "revenue", "capital"),
        ("grant", "eu_fund", "procurement", "competition", "corporate_open_call"),
        "Official EISMEA pages currently publish grants, open/upcoming calls and tenders.",
    ),
    ExpandedSource(
        "bip.gov.pl", "Biuletyn Informacji Publicznej", "official", "PL", "public_bulletin",
        ("funding", "revenue", "assets", "off_market"),
        ("procurement", "public_auction", "asset_sale", "regional_fund", "classified_offer"),
        "Public-information bulletin discovery root; individual local notices still require source-level verification.",
    ),
)


SOURCE_CLASSES = {
    "public_bulletin": {
        "families": {"funding", "revenue", "assets", "off_market", "local"},
        "country": "PL",
        "template": "site:bip.gov.pl {query} ogłoszenie nabór konkurs przetarg sprzedaż licytacja",
        "trust": "official_discovery_surface",
    },
    "regional_authority": {
        "families": {"funding", "finance", "savings", "assets", "revenue", "off_market"},
        "country": "PL",
        "template": "{query} urząd marszałkowski województwo nabór dotacja pożyczka przetarg sprzedaż",
        "trust": "source_class_discovery",
    },
    "local_government": {
        "families": {"funding", "assets", "revenue", "local", "off_market"},
        "country": "PL",
        "template": "{query} gmina powiat BIP nabór przetarg sprzedaż majątku lokal",
        "trust": "source_class_discovery",
    },
    "university_transfer": {
        "families": {"funding", "revenue", "off_market", "capital"},
        "country": "PL",
        "template": "site:edu.pl {query} centrum transferu technologii partner konkurs wdrożenie licencja",
        "trust": "institutional_discovery",
    },
    "chamber_association": {
        "families": {"revenue", "markets", "off_market", "funding"},
        "country": "PL",
        "template": "{query} izba gospodarcza partner biznesowy zapytanie dostawca konkurs eksport",
        "trust": "association_discovery",
    },
    "ngo_foundation": {
        "families": {"funding", "revenue", "off_market"},
        "country": "PL",
        "template": "{query} fundacja stowarzyszenie grant konkurs otwarty nabór partner",
        "trust": "nonprofit_discovery",
    },
    "insolvency_assets": {
        "families": {"assets", "local", "off_market"},
        "country": "PL",
        "template": "{query} syndyk upadłość likwidacja sprzedaż majątku maszyny nieruchomość",
        "trust": "market_legal_notice_discovery",
    },
    "supplier_rfq": {
        "families": {"revenue", "off_market", "local"},
        "country": "PL",
        "template": "{query} zapytanie ofertowe poszukuje dostawcy wykonawcy podwykonawcy RFQ",
        "trust": "commercial_demand_discovery",
    },
    "corporate_open_call": {
        "families": {"funding", "capital", "revenue", "off_market"},
        "country": "INTL",
        "template": "{query} corporate open call startup challenge supplier innovation partner",
        "trust": "corporate_discovery",
    },
    "eu_partnering": {
        "families": {"revenue", "markets", "off_market", "funding"},
        "country": "EU",
        "template": "site:een.ec.europa.eu/partnering-opportunities {query}",
        "trust": "official_database",
    },
    "research_jobs_funding": {
        "families": {"funding", "revenue"},
        "country": "EU",
        "template": "site:euraxess.ec.europa.eu {query} funding job hosting fellowship",
        "trust": "official_database",
    },
    "eu_sme_agency": {
        "families": {"funding", "revenue", "capital"},
        "country": "EU",
        "template": "site:eismea.ec.europa.eu {query} funding opportunities calls tenders",
        "trust": "official_database",
    },
    "public_finance": {
        "families": {"finance", "funding", "assets"},
        "country": "PL",
        "template": "site:arp.pl {query} finansowanie pożyczka leasing gwarancja inwestycja",
        "trust": "public_agency",
    },
    "export_trade": {
        "families": {"revenue", "savings", "markets", "off_market"},
        "country": "PL",
        "template": "site:paih.gov.pl {query} eksport partner dostawca inwestycja rynek",
        "trust": "official_agency",
    },
}


def _host(value: object) -> str:
    raw = str(value or "").strip().lower()
    if "://" not in raw:
        return raw.removeprefix("www.").split("/", 1)[0]
    try:
        return (urlsplit(raw).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def expanded_source_for_host(value: object) -> dict | None:
    host = _host(value)
    matches = [item for item in EXPANDED_SOURCES if host == item.domain or host.endswith("." + item.domain)]
    if not matches:
        return None
    item = sorted(matches, key=lambda row: len(row.domain), reverse=True)[0]
    return {
        "domain": item.domain, "name": item.name, "tier": item.tier, "country": item.country,
        "source_class": item.source_class, "families": list(item.families), "types": list(item.types),
        "evidence_note": item.evidence_note,
    }


def _class_order(profile: dict) -> list[str]:
    families = set(profile.get("requested_families") or [])
    if not families:
        return ["public_bulletin", "supplier_rfq", "insolvency_assets", "eu_partnering", "export_trade"]
    scored = []
    for index, (name, spec) in enumerate(SOURCE_CLASSES.items()):
        overlap = len(families & set(spec["families"]))
        geography = 1 if spec["country"] in {profile.get("country"), "EU", "INTL"} else 0
        scored.append((overlap, geography, -index, name))
    scored.sort(reverse=True)
    return [name for overlap, _, _, name in scored if overlap > 0]


def build_source_expansion_lanes(profile: dict, *, max_lanes: int = MAX_SOURCE_EXPANSION_LANES) -> list[dict]:
    query = " ".join(str(profile.get("query") or "").split())
    if not query:
        return []
    max_lanes = max(0, min(MAX_SOURCE_EXPANSION_LANES, int(max_lanes)))
    output = []
    seen = set()
    for source_class in _class_order(profile):
        if len(output) >= max_lanes:
            break
        spec = SOURCE_CLASSES[source_class]
        lane_query = " ".join(spec["template"].format(query=query).split())
        key = lane_query.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append({
            "lane": "source_class_expansion",
            "source_class": source_class,
            "query": lane_query,
            "country": spec["country"],
            "trust": spec["trust"],
            "families": sorted(spec["families"]),
        })
    return output


def source_expansion_capabilities() -> dict:
    return {
        "version": SOURCE_EXPANSION_VERSION,
        "expanded_registry_count": len(EXPANDED_SOURCES),
        "source_class_count": len(SOURCE_CLASSES),
        "max_source_class_lanes": MAX_SOURCE_EXPANSION_LANES,
        "source_classes": list(SOURCE_CLASSES),
        "officiality_means_listing_verified": False,
        "dynamic_source_discovery": True,
        "truth_semantics": "source_registry_and_class_queries_are_discovery_hints_not_opportunity_verification",
    }


__all__ = [
    "EXPANDED_SOURCES", "MAX_SOURCE_EXPANSION_LANES", "SOURCE_CLASSES", "SOURCE_EXPANSION_VERSION",
    "build_source_expansion_lanes", "expanded_source_for_host", "source_expansion_capabilities",
]
