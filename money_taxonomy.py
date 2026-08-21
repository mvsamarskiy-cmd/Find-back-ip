"""Deterministic taxonomy for Money / Material Opportunity Intelligence v2.

The taxonomy is intentionally broader than grants.  It covers legal/publicly
retrievable ways to obtain capital, revenue, assets, savings or economically
useful access.  Classification is evidence routing only: matching a type does
not prove that an opportunity is active, profitable or available to the user.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


MONEY_TAXONOMY_VERSION = "money-taxonomy-v2"


@dataclass(frozen=True)
class MoneyType:
    id: str
    family: str
    economic_kind: str
    repayable: bool | None
    patterns: tuple[str, ...]
    speed: int
    effort: int
    capital_required: int
    competition: int


# Scores use a simple 1..5 ordinal scale.  They are priors only and are exposed
# as such by the ranker; evidence from a concrete call/deal must dominate them.
_TYPES = (
    MoneyType("grant", "funding", "non_repayable", False, (r"\bgrant\w*\b", r"\bdotacj\w*\b", r"\bгрант\w*\b"), 2, 4, 2, 4),
    MoneyType("subsidy", "funding", "non_repayable", False, (r"\bsubsid\w*\b", r"\bdofinansowan\w*\b", r"\bдотац\w*\b", r"\bсубсид\w*\b"), 2, 4, 2, 4),
    MoneyType("public_aid", "funding", "non_repayable_or_mixed", None, (r"\bpublic aid\b", r"\bpomoc publiczn\w*\b", r"\bдержавн\w* допомог\w*\b"), 2, 4, 2, 4),
    MoneyType("eu_fund", "funding", "non_repayable_or_mixed", None, (r"\beu fund\w*\b", r"\bfundusz\w* europej\w*\b", r"\bfundusze europejskie\b", r"\bєвропейськ\w* фонд\w*\b"), 2, 4, 2, 4),
    MoneyType("regional_fund", "funding", "non_repayable_or_mixed", None, (r"\bregional\w* fund\w*\b", r"\bregionaln\w* program\w*\b", r"\bwojew[oó]dztw\w*\b", r"\bрегіональн\w* програм\w*\b"), 2, 4, 2, 3),
    MoneyType("competition", "funding", "prize", False, (r"\bcompetition\w*\b", r"\bkonkurs\w*\b", r"\bконкурс\w*\b"), 3, 3, 1, 4),
    MoneyType("prize", "funding", "prize", False, (r"\bcash prize\b", r"\bnagrod\w* pien\w*\b", r"\bгрошов\w* приз\w*\b"), 3, 3, 1, 4),
    MoneyType("challenge", "funding", "prize", False, (r"\bchallenge\w*\b", r"\bwyzwan\w*\b", r"\bчелендж\w*\b"), 3, 3, 1, 4),
    MoneyType("bounty", "funding", "bounty", False, (r"\bbount(?:y|ies)\b", r"\bnagrod\w* za rozwi[aą]zan\w*\b", r"\bбаунт\w*\b"), 4, 3, 1, 4),
    MoneyType("accelerator", "capital", "mixed_support", None, (r"\baccelerator\w*\b", r"\bakcelerator\w*\b", r"\bакселератор\w*\b"), 3, 3, 1, 4),
    MoneyType("incubator", "capital", "mixed_support", None, (r"\bincubator\w*\b", r"\binkubator\w*\b", r"\bінкубатор\w*\b"), 3, 3, 1, 3),
    MoneyType("scholarship", "funding", "stipend", False, (r"\bscholarship\w*\b", r"\bstypendi\w*\b", r"\bстипенд\w*\b"), 2, 3, 1, 4),
    MoneyType("fellowship", "funding", "stipend", False, (r"\bfellowship\w*\b", r"\bsta[zż]\w* badawcz\w*\b", r"\bфеллоушип\w*\b"), 2, 3, 1, 4),
    MoneyType("research_funding", "funding", "non_repayable_or_mixed", None, (r"\bresearch funding\b", r"\bgrant\w* badawcz\w*\b", r"\bfinansowan\w* bada[nń]\b", r"\bфінансув\w* дослідж\w*\b"), 2, 4, 2, 4),
    MoneyType("corporate_open_call", "funding", "mixed_support", None, (r"\bopen call\b", r"\bcorporate challenge\b", r"\bprogram partnersk\w*\b", r"\bвідкрит\w* набір\b"), 3, 3, 1, 3),
    MoneyType("paid_open_call", "revenue", "paid_call", False, (r"\bpaid open call\b", r"\bp[łl]atn\w* open call\b", r"\bоплачуван\w* open call\b"), 3, 3, 1, 3),

    MoneyType("vc", "capital", "equity", False, (r"\bventure capital\b", r"\b\bvc\b", r"\bfundusz\w* vc\b", r"\bвенчур\w* фонд\w*\b"), 2, 4, 1, 5),
    MoneyType("angel", "capital", "equity", False, (r"\bangel investor\w*\b", r"\banio[łl]\w* biznesu\b", r"\bбізнес.?ангел\w*\b"), 2, 4, 1, 5),
    MoneyType("equity_program", "capital", "equity", False, (r"\bequity program\w*\b", r"\binvestment program\w*\b", r"\bprogram inwestycyjn\w*\b", r"\bінвестиційн\w* програм\w*\b"), 2, 4, 1, 5),
    MoneyType("crowdfunding", "capital", "equity_or_reward", None, (r"\bcrowdfund\w*\b", r"\bfinansowanie spo[łl]eczno\w*\b", r"\bкраудфанд\w*\b"), 3, 4, 2, 4),

    MoneyType("preferential_loan", "finance", "loan", True, (r"\bpreferential loan\w*\b", r"\bsoft loan\w*\b", r"\bpo[zż]yczk\w* preferencyjn\w*\b", r"\bпільгов\w* кредит\w*\b"), 3, 3, 3, 3),
    MoneyType("guarantee", "finance", "guarantee", None, (r"\bloan guarantee\w*\b", r"\bgwarancj\w*\b", r"\bpor[eę]czen\w*\b", r"\bгаранті\w* кредит\w*\b"), 3, 3, 2, 3),
    MoneyType("leasing", "finance", "leasing", True, (r"\bleasing\w*\b", r"\bleasing\w*\b", r"\bлізинг\w*\b"), 4, 2, 2, 2),
    MoneyType("factoring", "finance", "factoring", True, (r"\bfactor(?:ing)?\b", r"\bfaktoring\w*\b", r"\bфакторинг\w*\b"), 4, 2, 2, 2),
    MoneyType("equipment_financing", "finance", "asset_finance", True, (r"\bequipment financ\w*\b", r"\bfinansowan\w* maszyn\w*\b", r"\bfinansowan\w* sprz[eę]t\w*\b", r"\bфінансув\w* обладнан\w*\b"), 3, 3, 3, 3),
    MoneyType("tax_relief", "savings", "tax_relief", False, (r"\btax (?:credit|relief|deduction)\b", r"\bulg\w* podatkow\w*\b", r"\bподатков\w* пільг\w*\b"), 3, 3, 1, 2),
    MoneyType("reimbursement", "savings", "reimbursement", False, (r"\breimburse\w*\b", r"\brefund\w*\b", r"\brefundacj\w*\b", r"\bzwrot koszt\w*\b", r"\bвідшкодуван\w*\b"), 3, 3, 2, 3),
    MoneyType("employment_incentive", "savings", "employment_support", False, (r"\bemployment incentive\w*\b", r"\bdop[łl]at\w* do zatrudn\w*\b", r"\brefundacj\w* zatrudn\w*\b", r"\bдотац\w* працевлаштуван\w*\b"), 3, 3, 1, 3),
    MoneyType("training_support", "savings", "training_support", False, (r"\btraining support\b", r"\bdofinansowan\w* szkol\w*\b", r"\bkfs\b", r"\bфінансув\w* навчан\w*\b"), 3, 2, 1, 3),
    MoneyType("export_support", "savings", "export_support", None, (r"\bexport support\b", r"\bwsparci\w* eksport\w*\b", r"\bекспортн\w* підтрим\w*\b"), 2, 3, 2, 3),
    MoneyType("innovation_voucher", "savings", "voucher", False, (r"\binnovation voucher\w*\b", r"\bbon\w* na innowac\w*\b", r"\bваучер\w* інновац\w*\b"), 2, 3, 1, 3),
    MoneyType("green_energy_support", "savings", "subsidy_or_finance", None, (r"\benergy efficien\w* support\b", r"\bgreen energy\w* support\b", r"\boze\b", r"\befektywno[śs]\w* energetycz\w*\b", r"\bенергоефектив\w* підтрим\w*\b"), 2, 4, 2, 3),

    MoneyType("procurement", "revenue", "contract_revenue", False, (r"\bprocurement\w*\b", r"\btender\w*\b", r"\bprzetarg\w*\b", r"\bzam[oó]wien\w* publiczn\w*\b", r"\bтендер\w*\b", r"\bзакупівл\w*\b"), 3, 4, 2, 4),
    MoneyType("job_contract", "revenue", "earned_income", False, (r"\bjob contract\w*\b", r"\bcontract work\b", r"\bzlecen\w*\b", r"\bofert\w* prac\w*\b", r"\bконтракт\w* робот\w*\b"), 4, 2, 1, 3),
    MoneyType("subcontract", "revenue", "contract_revenue", False, (r"\bsubcontract\w*\b", r"\bpodwykonawc\w*\b", r"\bпідряд\w*\b", r"\bсубпідряд\w*\b"), 4, 3, 2, 3),
    MoneyType("supplier_demand", "revenue", "sales_demand", False, (r"\bsupplier wanted\b", r"\blooking for supplier\b", r"\bszukam dostawc\w*\b", r"\bzapotrzebowan\w* dostawc\w*\b", r"\bшука\w* постачальник\w*\b"), 4, 2, 2, 2),

    MoneyType("business_for_sale", "assets", "asset_acquisition", None, (r"\bbusiness for sale\b", r"\bsprzedam firm\w*\b", r"\bgotow\w* biznes\w*\b", r"\bбізнес.*продаж\b"), 3, 3, 5, 3),
    MoneyType("asset_sale", "assets", "asset_acquisition", None, (r"\basset sale\b", r"\bsprzeda[zż] maj[aą]tk\w*\b", r"\bsprzeda[zż] maszyn\w*\b", r"\bпродаж\w* актив\w*\b", r"\bпродаж\w* обладнан\w*\b"), 4, 2, 3, 2),
    MoneyType("liquidation", "assets", "distressed_asset", None, (r"\bliquidation sale\b", r"\bliquidation stock\b", r"\blikwi?dacj\w*\b", r"\bwyprzeda[zż] likwidacyjn\w*\b", r"\bліквідаційн\w* продаж\w*\b"), 4, 2, 3, 2),
    MoneyType("real_estate_opportunity", "assets", "real_estate", None, (r"\bdistressed real estate\b", r"\bnieruchomo[śs]\w* okazj\w*\b", r"\bforeclosure\w*\b", r"\bнерухом\w* аукціон\w*\b"), 3, 3, 5, 3),
    MoneyType("public_auction", "assets", "auction", None, (r"\bpublic auction\b", r"\bauction notice\b", r"\blicytacj\w*\b", r"\baukcj\w* publiczn\w*\b", r"\bпублічн\w* аукціон\w*\b"), 4, 2, 3, 3),
    MoneyType("classified_offer", "local", "market_offer", None, (r"\bclassified\w*\b", r"\bog[łl]oszen\w*\b", r"\bolx\b", r"\bоголошен\w*\b"), 5, 1, 2, 2),
    MoneyType("wholesale_closeout", "local", "inventory_arbitrage_candidate", None, (r"\bcloseout\w*\b", r"\bwholesale lot\w*\b", r"\bko[nń]c[oó]wk\w* seri\w*\b", r"\bwyprzeda[zż] hurtow\w*\b", r"\bсток\w* опт\w*\b"), 4, 2, 3, 2),
    MoneyType("import_export_gap", "markets", "trade_gap_candidate", None, (r"\bimport.?export gap\b", r"\bimport opportunity\b", r"\bexport opportunity\b", r"\bluka rynkow\w*\b", r"\bдефіцит\w* імпорт\w*\b"), 2, 4, 4, 3),
    MoneyType("market_dislocation", "markets", "market_signal", None, (r"\bmarket dislocation\b", r"\bprice discrepancy\b", r"\bspread opportunity\b", r"\banomali\w* cen\w*\b", r"\bринков\w* аномал\w*\b"), 3, 4, 4, 4),
    MoneyType("off_market_public", "off_market", "publicly_obscure_signal", None, (r"\boff.?market\b", r"\bnot publicly listed\b", r"\bpoza rynkiem\b", r"\bniszow\w* og[łl]oszen\w*\b", r"\bпозаринков\w*\b"), 3, 4, 3, 2),
    MoneyType("other_monetizable_signal", "other", "unknown", None, (r"\bmonetiz\w*\b", r"\bzarobi\w*\b", r"\bdoch[oó]d\w*\b", r"\bзароб\w*\b", r"\bдохід\w*\b"), 3, 3, 2, 3),
)

TYPE_BY_ID = {item.id: item for item in _TYPES}
FAMILIES = tuple(dict.fromkeys(item.family for item in _TYPES))
TYPE_IDS = tuple(item.id for item in _TYPES)


# Strong action/context phrases.  These prevent educational queries such as
# "What is investment banking?" from being routed into opportunity search.
_ACTION_PATTERNS = (
    r"\bfind\w*\b", r"\blooking for\b", r"\bavailable\b", r"\bopen now\b", r"\bapply\w*\b",
    r"\bneed\w*\b", r"\bwant to (?:raise|get|earn|buy|sell|finance)\b", r"\bwhere can i\b",
    r"\bznajd\w*\b", r"\bszuk\w*\b", r"\bdost[eę]pn\w*\b", r"\bpotrzeb\w*\b", r"\bchc[eę]\b",
    r"\bзнайд\w*\b", r"\bшука\w*\b", r"\bдоступн\w*\b", r"\bпотріб\w*\b", r"\bхочу\b", r"\bде (?:взяти|знайти|отримати|заробити|купити)\b",
)

_NEED_PATTERNS = (
    r"\bequipment\b", r"\bmachin(?:e|ery)\b", r"\bworking capital\b", r"\bstartup\b", r"\bsme\b",
    r"\bmanufactur\w*\b", r"\bexport\b", r"\btraining\b", r"\bemploy\w*\b", r"\breal estate\b",
    r"\bsprz[eę]t\w*\b", r"\bmaszyn\w*\b", r"\bkapita[łl] obrotow\w*\b", r"\bprodukc\w*\b", r"\beksport\w*\b",
    r"\bобладнан\w*\b", r"\bвиробниц\w*\b", r"\bоборотн\w* капітал\w*\b", r"\bекспорт\w*\b",
)


def _text(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def infer_money_types(query: object, *, limit: int = 8) -> list[str]:
    """Return evidence-routing money types in deterministic confidence order."""
    text = _text(query)
    scored: list[tuple[int, int, str]] = []
    for index, item in enumerate(_TYPES):
        hits = sum(1 for pattern in item.patterns if re.search(pattern, text, flags=re.I))
        if hits:
            scored.append((hits, -index, item.id))
    scored.sort(reverse=True)
    return [item_id for _, _, item_id in scored[: max(1, int(limit))]]


def infer_money_families(query: object, *, limit: int = 5) -> list[str]:
    families = []
    for item_id in infer_money_types(query, limit=20):
        family = TYPE_BY_ID[item_id].family
        if family not in families:
            families.append(family)
    return families[: max(1, int(limit))]


def looks_like_material_opportunity(query: object) -> bool:
    """High-confidence router predicate for actionable money/material searches."""
    text = _text(query)
    if not text:
        return False
    type_hits = infer_money_types(text, limit=20)
    has_action = any(re.search(pattern, text, flags=re.I) for pattern in _ACTION_PATTERNS)
    if type_hits and has_action:
        return True
    # Natural-language needs often omit mechanism words.  Route them only when
    # both a tangible need and an action/need signal are present.
    has_need_subject = any(re.search(pattern, text, flags=re.I) for pattern in _NEED_PATTERNS)
    money_need = bool(re.search(r"(?:\b\d[\d\s.,]*\s*(?:pln|eur|usd|z[łl]|€|\$)\b|\b(?:money|capital|financ\w*|fund\w*|pieni[aą]d\w*|kapita[łl]\w*|finans\w*|грош\w*|капітал\w*|фінанс\w*)\b)", text, flags=re.I))
    return bool(has_action and has_need_subject and money_need)


def taxonomy_capabilities() -> dict:
    return {
        "version": MONEY_TAXONOMY_VERSION,
        "families": list(FAMILIES),
        "types": list(TYPE_IDS),
        "type_count": len(TYPE_IDS),
        "truth_semantics": "taxonomy_match_is_routing_evidence_not_opportunity_verification",
    }


__all__ = [
    "FAMILIES", "MONEY_TAXONOMY_VERSION", "MoneyType", "TYPE_BY_ID", "TYPE_IDS",
    "infer_money_families", "infer_money_types", "looks_like_material_opportunity",
    "taxonomy_capabilities",
]
