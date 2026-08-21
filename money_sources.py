"""Curated source affinity catalog for Money / Material Opportunity Intelligence.

Catalog membership affects discovery/ranking only.  It never means an individual
listing/call is current, complete, authentic, profitable or available to a user.
"""
from __future__ import annotations

from urllib.parse import urlsplit


MONEY_SOURCE_CATALOG_VERSION = "money-source-catalog-v2"


# family/type affinity is deliberately many-to-many.  Official/public sources
# are preferred for legal status and current calls; market/platform sources are
# useful discovery evidence but never receive official-source semantics.
SOURCE_CATALOG = (
    # EU / public funding and procurement
    {"domain": "funding-tenders.ec.europa.eu", "name": "EU Funding & Tenders Portal", "tier": "official", "country": "EU", "families": ("funding", "revenue"), "types": ("grant", "eu_fund", "research_funding", "procurement")},
    {"domain": "ted.europa.eu", "name": "Tenders Electronic Daily", "tier": "official", "country": "EU", "families": ("revenue",), "types": ("procurement", "subcontract")},
    {"domain": "eic.ec.europa.eu", "name": "European Innovation Council", "tier": "official", "country": "EU", "families": ("funding", "capital"), "types": ("grant", "accelerator", "equity_program")},
    {"domain": "eit.europa.eu", "name": "European Institute of Innovation and Technology", "tier": "official", "country": "EU", "families": ("funding", "capital"), "types": ("grant", "accelerator", "competition", "corporate_open_call")},
    {"domain": "eib.org", "name": "European Investment Bank", "tier": "official", "country": "EU", "families": ("finance", "capital"), "types": ("preferential_loan", "guarantee", "equipment_financing")},
    {"domain": "eif.org", "name": "European Investment Fund", "tier": "official", "country": "EU", "families": ("finance", "capital"), "types": ("guarantee", "vc", "equity_program")},
    {"domain": "interreg.eu", "name": "Interreg", "tier": "official", "country": "EU", "families": ("funding",), "types": ("eu_fund", "regional_fund", "grant")},
    {"domain": "erasmus-plus.ec.europa.eu", "name": "Erasmus+", "tier": "official", "country": "EU", "families": ("funding", "savings"), "types": ("grant", "scholarship", "training_support")},
    {"domain": "cordis.europa.eu", "name": "CORDIS", "tier": "official", "country": "EU", "families": ("funding",), "types": ("research_funding", "eu_fund")},
    {"domain": "commission.europa.eu", "name": "European Commission", "tier": "official", "country": "EU", "families": ("funding", "finance", "savings", "revenue"), "types": ()},
    {"domain": "europa.eu", "name": "European Union", "tier": "official", "country": "EU", "families": ("funding", "finance", "savings", "revenue"), "types": ()},

    # Poland public / quasi-public
    {"domain": "funduszeeuropejskie.gov.pl", "name": "Fundusze Europejskie", "tier": "official", "country": "PL", "families": ("funding", "finance", "savings"), "types": ("grant", "subsidy", "eu_fund", "regional_fund", "preferential_loan")},
    {"domain": "parp.gov.pl", "name": "PARP", "tier": "official", "country": "PL", "families": ("funding", "capital", "savings"), "types": ("grant", "accelerator", "innovation_voucher", "export_support", "training_support")},
    {"domain": "ncbr.gov.pl", "name": "NCBR", "tier": "official", "country": "PL", "families": ("funding",), "types": ("grant", "research_funding", "eu_fund")},
    {"domain": "bgk.pl", "name": "BGK", "tier": "official", "country": "PL", "families": ("finance", "funding"), "types": ("preferential_loan", "guarantee", "equipment_financing", "green_energy_support")},
    {"domain": "pfr.pl", "name": "Polski Fundusz Rozwoju", "tier": "public", "country": "PL", "families": ("capital", "finance", "funding"), "types": ("vc", "equity_program", "accelerator", "guarantee")},
    {"domain": "biznes.gov.pl", "name": "Biznes.gov.pl", "tier": "official", "country": "PL", "families": ("funding", "finance", "savings"), "types": ("public_aid", "tax_relief", "reimbursement", "employment_incentive")},
    {"domain": "gov.pl", "name": "Gov.pl", "tier": "official", "country": "PL", "families": ("funding", "finance", "savings", "assets", "revenue"), "types": ()},
    {"domain": "praca.gov.pl", "name": "Praca.gov.pl", "tier": "official", "country": "PL", "families": ("savings", "revenue"), "types": ("employment_incentive", "training_support", "job_contract")},
    {"domain": "arimr.gov.pl", "name": "ARiMR", "tier": "official", "country": "PL", "families": ("funding", "finance"), "types": ("grant", "subsidy", "preferential_loan")},
    {"domain": "nfosigw.gov.pl", "name": "NFOŚiGW", "tier": "official", "country": "PL", "families": ("funding", "finance", "savings"), "types": ("grant", "preferential_loan", "green_energy_support", "reimbursement")},
    {"domain": "ezamowienia.gov.pl", "name": "e-Zamówienia", "tier": "official", "country": "PL", "families": ("revenue",), "types": ("procurement", "subcontract")},
    {"domain": "bazakonkurencyjnosci.funduszeeuropejskie.gov.pl", "name": "Baza Konkurencyjności", "tier": "official", "country": "PL", "families": ("revenue",), "types": ("procurement", "supplier_demand", "subcontract")},
    {"domain": "krz.ms.gov.pl", "name": "Krajowy Rejestr Zadłużonych", "tier": "official", "country": "PL", "families": ("assets", "off_market"), "types": ("liquidation", "asset_sale", "business_for_sale", "public_auction")},
    {"domain": "licytacje.komornik.pl", "name": "Licytacje Komornicze", "tier": "public", "country": "PL", "families": ("assets", "off_market"), "types": ("public_auction", "asset_sale", "real_estate_opportunity")},

    # Investment / startup / challenges
    {"domain": "f6s.com", "name": "F6S", "tier": "platform", "country": "INTL", "families": ("capital", "funding"), "types": ("accelerator", "incubator", "corporate_open_call", "competition")},
    {"domain": "dealroom.co", "name": "Dealroom", "tier": "platform", "country": "INTL", "families": ("capital",), "types": ("vc", "angel", "equity_program")},
    {"domain": "herox.com", "name": "HeroX", "tier": "platform", "country": "INTL", "families": ("funding",), "types": ("challenge", "prize", "competition", "bounty")},
    {"domain": "xprize.org", "name": "XPRIZE", "tier": "platform", "country": "INTL", "families": ("funding",), "types": ("challenge", "prize", "competition")},
    {"domain": "kaggle.com", "name": "Kaggle", "tier": "platform", "country": "INTL", "families": ("funding", "revenue"), "types": ("competition", "prize", "bounty")},
    {"domain": "challenge.gov", "name": "Challenge.gov", "tier": "official", "country": "INTL", "families": ("funding",), "types": ("challenge", "competition", "prize")},

    # Revenue / contracts
    {"domain": "useme.com", "name": "Useme", "tier": "platform", "country": "PL", "families": ("revenue",), "types": ("job_contract", "subcontract")},
    {"domain": "upwork.com", "name": "Upwork", "tier": "platform", "country": "INTL", "families": ("revenue",), "types": ("job_contract", "subcontract")},
    {"domain": "pracuj.pl", "name": "Pracuj.pl", "tier": "platform", "country": "PL", "families": ("revenue",), "types": ("job_contract",)},
    {"domain": "rocketjobs.pl", "name": "RocketJobs", "tier": "platform", "country": "PL", "families": ("revenue",), "types": ("job_contract",)},

    # Local / asset / market discovery
    {"domain": "olx.pl", "name": "OLX", "tier": "market", "country": "PL", "families": ("local", "assets"), "types": ("classified_offer", "asset_sale", "business_for_sale", "wholesale_closeout")},
    {"domain": "allegrolokalnie.pl", "name": "Allegro Lokalnie", "tier": "market", "country": "PL", "families": ("local", "assets"), "types": ("classified_offer", "asset_sale")},
    {"domain": "gratka.pl", "name": "Gratka", "tier": "market", "country": "PL", "families": ("local", "assets"), "types": ("classified_offer", "real_estate_opportunity", "business_for_sale")},
    {"domain": "otodom.pl", "name": "Otodom", "tier": "market", "country": "PL", "families": ("assets", "local"), "types": ("real_estate_opportunity", "classified_offer")},
)


def _host(url_or_host: object) -> str:
    raw = str(url_or_host or "").strip().lower()
    if "://" not in raw:
        return raw.removeprefix("www.").split("/", 1)[0]
    try:
        return (urlsplit(raw).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def source_for_host(url_or_host: object) -> dict | None:
    host = _host(url_or_host)
    matches = [row for row in SOURCE_CATALOG if host == row["domain"] or host.endswith("." + row["domain"])]
    if not matches:
        return None
    return dict(sorted(matches, key=lambda row: len(row["domain"]), reverse=True)[0])


def source_affinity(url_or_host: object, *, families=(), types=()) -> int:
    source = source_for_host(url_or_host)
    if not source:
        return 0
    requested_families = set(families or ())
    requested_types = set(types or ())
    score = {"official": 22, "public": 17, "platform": 10, "market": 7}.get(source["tier"], 4)
    if requested_families & set(source.get("families") or ()):
        score += 8
    if requested_types & set(source.get("types") or ()):
        score += 10
    return min(40, score)


def sources_for(*, country="EU", families=(), types=(), limit=12) -> list[dict]:
    country = str(country or "EU").upper()
    family_set, type_set = set(families or ()), set(types or ())
    rows = []
    for row in SOURCE_CATALOG:
        if country != "EU" and row["country"] not in {country, "EU", "INTL"}:
            continue
        if family_set and not (family_set & set(row.get("families") or ())):
            continue
        if type_set and row.get("types") and not (type_set & set(row.get("types") or ())):
            continue
        rows.append(dict(row))
    rows.sort(key=lambda row: ({"official": 0, "public": 1, "platform": 2, "market": 3}.get(row["tier"], 9), row["domain"]))
    return rows[: max(1, int(limit))]


def source_catalog_capabilities() -> dict:
    return {
        "version": MONEY_SOURCE_CATALOG_VERSION,
        "source_count": len(SOURCE_CATALOG),
        "tiers": sorted({row["tier"] for row in SOURCE_CATALOG}),
        "countries": sorted({row["country"] for row in SOURCE_CATALOG}),
        "truth_semantics": "catalog_affinity_is_discovery_ranking_not_listing_verification",
    }


__all__ = [
    "MONEY_SOURCE_CATALOG_VERSION", "SOURCE_CATALOG", "source_affinity",
    "source_catalog_capabilities", "source_for_host", "sources_for",
]
