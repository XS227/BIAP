"""European ESEF/UKSEF fundamentals adapter for BIAP Global.

The adapter uses LEI as the legal-entity join key and reads xBRL-JSON from the
public filings.xbrl.org repository. It is intentionally conservative:

- explicit LEI is verified through GLEIF; otherwise only an unambiguous exact
  legal-name GLEIF match is accepted;
- only standard IFRS concepts are normalized;
- dimensioned/segment facts are rejected for headline metrics;
- annual duration facts are preferred; missing concepts remain None;
- filing validation errors reduce source quality rather than being ignored.

filings.xbrl.org is an independent public index of ESEF/UKSEF filings, not the
issuer's primary regulator. Provenance keeps both the filing/index URLs so BIAP
can later replace or corroborate it with country OAM/regulator adapters.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import re
from typing import Any, Optional

import httpx

import json
from pathlib import Path

from .gleif import GLEIFResolver
from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source

FILINGS_API = "https://filings.xbrl.org/api/filings"

_REVIEWED_CAPEX_PATH = Path(__file__).with_name("data") / "reviewed_capex_lines.json"


def _reviewed_capex_lines() -> dict[str, dict]:
    """LEI -> reviewed capex-line mapping (empty when the file is absent/unreadable)."""
    try:
        payload = json.loads(_REVIEWED_CAPEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(row["lei"]).upper(): row for row in payload.get("issuers", []) if isinstance(row, dict) and row.get("lei") and row.get("concept")}

_REVIEWED_DA_PATH = Path(__file__).with_name("data") / "reviewed_da_lines.json"


def _reviewed_da_lines() -> dict[str, dict]:
    """LEI -> reviewed D&A cash-flow lines tagged with extension concepts."""
    try:
        payload = json.loads(_REVIEWED_DA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(row["lei"]).upper(): row for row in payload.get("issuers", [])
            if isinstance(row, dict) and row.get("lei") and row.get("concepts")}


_CONCEPTS = {
    "revenue": ("ifrs-full:Revenue", "ifrs-full:RevenueFromContractsWithCustomers"),
    "gross_profit": ("ifrs-full:GrossProfit",),
    "operating_income": ("ifrs-full:ProfitLossFromOperatingActivities", "ifrs-full:OperatingProfitLoss"),
    "ebitda": (),
    "depreciation_amortisation": (
        "ifrs-full:DepreciationAndAmortisationExpense",
        "ifrs-full:DepreciationAndAmortizationExpense",
        "ifrs-full:DepreciationExpense",
    ),
    "net_income": ("ifrs-full:ProfitLoss",),
    # Owners'-share profit: EPS is per share of the parent's owners, so share
    # counts are cross-checked against this when the issuer tags it.
    "net_income_owners": ("ifrs-full:ProfitLossAttributableToOwnersOfParent",),
    "assets": ("ifrs-full:Assets",),
    "liabilities": ("ifrs-full:Liabilities",),
    "equity": ("ifrs-full:Equity",),
    "retained_earnings": ("ifrs-full:RetainedEarnings",),
    "current_assets": ("ifrs-full:CurrentAssets",),
    "current_liabilities": ("ifrs-full:CurrentLiabilities",),
    "cash": ("ifrs-full:CashAndCashEquivalents",),
    "ocf": ("ifrs-full:CashFlowsFromUsedInOperatingActivities",),
    # Pure D&A add-backs from the cash-flow statement (impairment-inclusive
    # variants are deliberately excluded).
    "depreciation_amortisation_cash_flow": (
        "ifrs-full:AdjustmentsForDepreciationAndAmortisationExpense",
    ),
    # Separately tagged D&A lines, summed only when no D&A total is tagged.
    "depreciation_amortisation_component": (
        "ifrs-full:AdjustmentsForDepreciationExpense",
        "ifrs-full:AdjustmentsForAmortisationExpense",
    ),
    "capex": (
        "ifrs-full:PurchaseOfPropertyPlantAndEquipment",
        "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "ifrs-full:PaymentsToAcquirePropertyPlantAndEquipment",
    ),
    "borrowings": (
        "ifrs-full:Borrowings",
        "ifrs-full:InterestBearingLoansAndBorrowings",
        "ifrs-full:LoansAndBorrowings",
    ),
    # IFRS taxonomy element names differ by preparer; Shell plc FY2025 tags
    # its balance-sheet "Debt" lines with LongtermBorrowings and
    # CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings.
    "current_borrowings": (
        "ifrs-full:CurrentBorrowings",
        "ifrs-full:CurrentInterestBearingLoansAndBorrowings",
        "ifrs-full:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",
    ),
    "noncurrent_borrowings": (
        "ifrs-full:NoncurrentBorrowings",
        "ifrs-full:NoncurrentInterestBearingLoansAndBorrowings",
        "ifrs-full:LongtermBorrowings",
    ),
    # Bonds issued and loans received (IFRS "loans received" lines, or issuer
    # "other loans") are separate debt lines on the balance sheet; they are
    # used only when no borrowings line is tagged (e.g. Volvo Car AB FY2025).
    "current_bonds": ("ifrs-full:CurrentBondsIssuedAndCurrentPortionOfNoncurrentBondsIssued",),
    "noncurrent_bonds": ("ifrs-full:NoncurrentPortionOfNoncurrentBondsIssued",),
    "current_other_loans": ("ifrs-full:CurrentLoansReceivedAndCurrentPortionOfNoncurrentLoansReceived",),
    "noncurrent_other_loans": ("ifrs-full:NoncurrentPortionOfNoncurrentLoansReceived",),
    "interest_expense": ("ifrs-full:FinanceCosts", "ifrs-full:InterestExpense"),
    # Used only to detect gross-up: issuers such as Eni tag derivative/FX
    # gross flows in FinanceCosts that are offset by a similar FinanceIncome.
    "interest_expense_only": ("ifrs-full:InterestExpense",),
    "finance_costs_only": ("ifrs-full:FinanceCosts",),
    "finance_income": ("ifrs-full:FinanceIncome",),
    "net_finance_cost": ("ifrs-full:FinanceIncomeCost",),
    # Cash-flow lines for the S&P-style FFO derivation (EBITDA - interest
    # paid + interest received - income taxes paid).
    "interest_paid": (
        "ifrs-full:InterestPaidClassifiedAsOperatingActivities",
        "ifrs-full:InterestPaidClassifiedAsFinancingActivities",
    ),
    "interest_received": (
        "ifrs-full:InterestReceivedClassifiedAsOperatingActivities",
        "ifrs-full:InterestReceivedClassifiedAsInvestingActivities",
    ),
    "income_taxes_paid": (
        "ifrs-full:IncomeTaxesPaidClassifiedAsOperatingActivities",
        "ifrs-full:IncomeTaxesPaidRefundClassifiedAsOperatingActivities",
    ),
    "eps": ("ifrs-full:BasicEarningsLossPerShare", "ifrs-full:DilutedEarningsLossPerShare"),
    # Issuer-reported shares outstanding (not "issued": treasury shares would
    # overstate it). Only the plain, undimensioned fact is read; per-class
    # facts are dimensioned and therefore never summed or guessed.
    "shares_outstanding": ("ifrs-full:NumberOfSharesOutstanding",),
    # Labelled fallback only (see _single_class_shares_issued): shares ISSUED
    # include treasury shares, so it is used solely when the filing tags no
    # outstanding count and no per-class facts exist at all.
    "shares_issued": ("ifrs-full:NumberOfSharesIssued",),
    # Continuing-operations EPS equals EPS only when no discontinued
    # operation result is tagged for the year (e.g. Komplett ASA FY2025).
    "eps_continuing": (
        "ifrs-full:BasicEarningsLossPerShareFromContinuingOperations",
        "ifrs-full:DilutedEarningsLossPerShareFromContinuingOperations",
    ),
    "discontinued_profit": ("ifrs-full:ProfitLossFromDiscontinuedOperations",),
    # Top line tagged as "revenue and operating income" (Norwegian "sum
    # driftsinntekter", e.g. Komplett, Scana, Axactor) when no IFRS Revenue
    # total is tagged; separately tagged other income is netted out.
    "revenue_and_operating_income": ("ifrs-full:RevenueAndOperatingIncome",),
    "other_operating_income": ("ifrs-full:OtherIncome", "ifrs-full:OtherOperatingIncome"),
    # Sale of goods is the whole top line only when no services revenue is
    # tagged for the year (e.g. Sildarvinnslan FY2024); otherwise it is a part.
    "revenue_sale_of_goods": ("ifrs-full:RevenueFromSaleOfGoods",),
    "revenue_rendering_of_services": ("ifrs-full:RevenueFromRenderingOfServices",),
    # Bank (Bank of Italy Circular 262) layout: no IFRS Revenue / Equity total
    # is tagged. These concepts let the normalizer use the issuer's own tagged
    # totals instead, and only under the bank guards in normalized_fields.
    "owners_equity": ("ifrs-full:EquityAttributableToOwnersOfParent",),
    "noncontrolling_interests": ("ifrs-full:NoncontrollingInterests",),
    "equity_and_liabilities": ("ifrs-full:EquityAndLiabilities",),
    "bank_operating_income": (),
    "bank_fee_income": ("ifrs-full:FeeAndCommissionIncomeExpense",),
    "bank_interest_revenue": ("ifrs-full:InterestRevenueCalculatedUsingEffectiveInterestMethod",),
}

_EXTENSION_LOCAL_PATTERNS = {
    "ebitda": (
        r"^ebitda$",
        r"^earningsbeforeinteresttax(?:es)?depreciationandamorti[sz]ation$",
        r"^operatingprofitbeforedepreciationandamorti[sz]ation$",
    ),
    "depreciation_amortisation": (
        r"^depreciationandamorti[sz]ation(?:expense|expenses)?$",
        r"^depreciationamorti[sz]ationandimpairment(?:expense|expenses)?$",
    ),
    # Swedish-language extension lines (e.g. AB Volvo abvolvo:Avskrivningar*):
    # depreciation/amortisation of intangible, tangible, leased and
    # right-of-use assets. Impairment ("nedskrivningar") is never matched.
    "depreciation_amortisation_component": (
        r"^avskrivningar(?:pa)?(?:immateriella|materiella|leasing|nyttjanderatts)[a-z]*$",
    ),
    "capex": (
        r"^investeringari(?:materiella)anlaggningstillgangar$",
    ),
    "current_other_loans": (r"^ovrigalankortfristigskuld$",),
    "noncurrent_other_loans": (r"^ovrigalanlangfristigskuld$",),
    "retained_earnings": (
        r"^retainedearnings(?:accumulatedlosses)?$",
        r"^retainedearningsaccumulatedloss$",
    ),
    "borrowings": (
        r"^(?:total|gross)?financialdebt$",
        r"^(?:total)?interestbearing(?:loansand)?borrowings$",
    ),
    "current_borrowings": (
        r"^currentfinancialdebt$",
        r"^currentinterestbearing(?:loansand)?borrowings$",
    ),
    "noncurrent_borrowings": (
        r"^noncurrentfinancialdebt$",
        r"^noncurrentinterestbearing(?:loansand)?borrowings$",
    ),
    "interest_expense": (
        r"^interestexpense$",
        r"^interestexpenses$",
        r"^financecosts$",
    ),
    # Issuer total of the equity section, e.g. isp:TotalEquity.
    "equity": (r"^totalequity$",),
    "owners_equity": (
        r"^(?:total)?equityattributabletoownersofparent(?:atendofperiod)?$",
    ),
    # Circular 262 item 120 "Margine di intermediazione" / "Net interest and
    # other banking income" (isp:GrossIncome, bperbanca:GrossIncome,
    # finecobank:MargineDiIntermediazione).
    "bank_operating_income": (
        r"^grossincome$",
        r"^netinterestandotherbankingincome$",
        r"^marginediintermediazione$",
    ),
    # Circular 262 item 10 "Interessi attivi e proventi assimilati".
    "bank_interest_revenue": (r"^interestincomeandsimilarrevenues$",),
}
_ALLOWED_DIMENSIONS = {"concept", "entity", "period", "unit"}
# The statement of changes in equity tags the owners' total column with this
# single IFRS member; any other axis/member is a component, never a total.
_OWNERS_TOTAL_DIMENSION = ("ifrs-full:ComponentsOfEquityAxis", "ifrs-full:EquityAttributableToOwnersOfParentMember")
# The same statement's non-controlling-interests column. A total-equity
# concept on exactly the owners column is owners' equity and on exactly this
# column is NCI (Banca Mediolanum ext:TotalEquity, Banca Profilo
# ifrs-full:Equity): owners + NCI columns = total equity under IFRS.
_NCI_DIMENSION = ("ifrs-full:ComponentsOfEquityAxis", "ifrs-full:NoncontrollingInterestsMember")
# The retained-earnings column of the same statement: a total-equity concept on
# exactly this column is the closing retained earnings balance.
_RETAINED_EARNINGS_DIMENSION = ("ifrs-full:ComponentsOfEquityAxis", "ifrs-full:RetainedEarningsMember")
_COMPONENTS_AXIS = "ifrs-full:ComponentsOfEquityAxis"
_RESTATEMENT_AXIS = "ifrs-full:RetrospectiveApplicationAndRetrospectiveRestatementAxis"
_PREVIOUSLY_STATED = "ifrs-full:PreviouslyStatedMember"
_EQUITY_TOTAL_MEMBERS = {
    "ifrs-full:equityattributabletoownersofparentmember",
    "ifrs-full:noncontrollinginterestsmember",
    "ifrs-full:equitymember",
}


def _concept_local_name(concept: object) -> str:
    text = str(concept or "").strip()
    return re.sub(r"[^A-Za-z0-9]", "", text.split(":", 1)[-1]).lower()


def _extension_key(concept: object) -> Optional[str]:
    local = _concept_local_name(concept)
    if not local:
        return None
    for key, patterns in _EXTENSION_LOCAL_PATTERNS.items():
        if any(re.fullmatch(pattern, local, flags=re.IGNORECASE) for pattern in patterns):
            return key
    return None


def concept_is_relevant(concept: object) -> bool:
    text = str(concept or "").strip().lower()
    if any(text == value.lower() for values in _CONCEPTS.values() for value in values):
        return True
    return _extension_key(concept) is not None


def _num(value: Any) -> Optional[float]:
    if value in (None, "", "nil", "NaN"):
        return None
    try:
        result = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    return None if result != result else result


def _period_point(text: str, *, is_end: bool) -> date:
    """Parse one xBRL period boundary as the *reporting* calendar date.

    xBRL-JSON (OIM) encodes period ends and instants as exclusive midnight
    datetimes: fiscal year 2025 is ``2025-01-01T00:00:00/2026-01-01T00:00:00``
    and a 31 Dec 2025 balance is ``2026-01-01T00:00:00``. Treating that
    exclusive end as the reporting date shifted every duration fact one fiscal
    year back (the FY2025 filing produced FY2024 revenue/profit). Date-only
    values (inline XBRL contexts) are already inclusive and stay unchanged.
    """
    value = text.strip()
    day = date.fromisoformat(value[:10])
    if is_end and len(value) > 10 and value[10:].startswith("T00:00:00"):
        day = day - timedelta(days=1)
    return day


def _period_parts(raw: Any) -> tuple[Optional[date], Optional[date]]:
    text = str(raw or "").strip()
    if not text:
        return None, None
    parts = text.split("/")
    try:
        if len(parts) == 1:
            instant = _period_point(parts[0], is_end=True)
            return instant, instant
        return _period_point(parts[0], is_end=False), _period_point(parts[-1], is_end=True)
    except ValueError:
        return None, None


def _agent10_fields(meta: dict) -> dict:
    """Expose a filing-derived FFO to Agent 10 with its derivation method."""
    ffo = (meta or {}).get("ffo")
    if ffo is None:
        return {}
    return {"agent10_ffo": ffo, "agent10_ffo_method": meta.get("ffo_method")}


def _unit_currency(raw: Any) -> Optional[str]:
    match = re.search(r"(?:iso4217:|currency:)([A-Z]{3})", str(raw or ""), re.IGNORECASE)
    return match.group(1).upper() if match else None


class ESEFFundamentalsProvider(FundamentalsProvider):
    provider_id = "esef-xbrl"

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.timeout = max(5.0, float(timeout))
        self.gleif = GLEIFResolver(timeout=min(self.timeout, 12.0))

    def _get_json(self, url: str, *, params: Optional[dict] = None) -> dict:
        try:
            with httpx.Client(timeout=self.timeout, headers={"Accept": "application/json", "User-Agent": "BIAP-Global/1.0 ESEF evidence"}) as client:
                response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"ESEF request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError("unexpected ESEF JSON response")
        return payload

    def _resolve_lei(self, company: GlobalCompany) -> tuple[str, str]:
        if company.lei:
            resolution = self.gleif.verify_lei(company.lei)
            return resolution.lei, resolution.legal_name
        # ISIN is a certified security-to-issuer identity key and is stronger
        # than abbreviated exchange display names (e.g. COOR, Catella A).
        if company.isin:
            try:
                resolution = self.gleif.resolve_isin(company.isin, country=company.country)
                return resolution.lei, resolution.legal_name
            except GlobalProviderError:
                pass
        if not company.name or company.name == company.ticker:
            raise GlobalProviderError("ESEF requires a verified LEI, ISIN, or full legal company name")
        resolution = self.gleif.resolve_exact_legal_name(company.name, country=company.country)
        return resolution.lei, resolution.legal_name

    def _latest_filing(self, lei: str, country: str) -> dict:
        payload = self._get_json(FILINGS_API, params={
            "filter[entity.identifier]": lei,
            "page[size]": 20,
            "page[number]": 1,
            "sort": "-period_end",
            "include": "entity",
        })
        rows = payload.get("data")
        if not isinstance(rows, list) or not rows:
            raise GlobalProviderError(f"no ESEF filing found for LEI {lei}")
        candidates: list[tuple[str, int, int, dict]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            attrs = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
            filing_country = str(attrs.get("country") or "").upper()
            country_penalty = 0 if not country or filing_country == country.upper() else 1
            period = str(attrs.get("period_end") or "")
            json_url = str(attrs.get("json_url") or "").strip()
            if not period or not json_url:
                continue
            # A report cannot cover a period that ends after it was filed.
            # Mis-indexed entries exist (Recordati 5011: the FY2022 report
            # indexed as 2032-12-31) and would otherwise sort first.
            filed = str(attrs.get("date_added") or attrs.get("processed") or "")[:10] or date.today().isoformat()
            if period[:10] > filed:
                continue
            try:
                errors = int(attrs.get("error_count") or 0)
            except (TypeError, ValueError):
                errors = 999
            candidates.append((period, -country_penalty, -errors, row))
        if not candidates:
            raise GlobalProviderError(f"ESEF filing index has no usable xBRL-JSON for LEI {lei}")
        candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return candidates[0][3]

    @staticmethod
    def _facts(payload: dict) -> list[dict]:
        raw = payload.get("facts")
        return [fact for fact in raw.values() if isinstance(fact, dict)] if isinstance(raw, dict) else []

    @staticmethod
    def _plain_fact(fact: dict) -> bool:
        dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
        return all(key in _ALLOWED_DIMENSIONS for key in dims)

    @classmethod
    def _concept_facts(cls, facts: list[dict], concepts: tuple[str, ...], *, extension_key: Optional[str] = None) -> list[dict]:
        wanted = {value.lower() for value in concepts}
        result = []
        for fact in facts:
            dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
            concept = str(dims.get("concept") or "")
            exact = concept.lower() in wanted
            extension = extension_key is not None and _extension_key(concept) == extension_key
            if (exact or extension) and cls._plain_fact(fact) and _num(fact.get("value")) is not None:
                result.append(fact)
        return result

    @classmethod
    def _interest_expense(cls, concept_facts: dict, period_end: date) -> Optional[float]:
        """Interest cost for coverage ratios, never a gross-up.

        A tagged InterestExpense wins. Gross FinanceCosts is used unless it is an
        extreme gross-up (Eni: costs 8.2bn vs income 7.2bn from derivatives/FX,
        net 0.8bn); then the issuer's own reported net finance cost is used
        when it is a cost, else the figure is withheld.
        """
        direct = cls._duration_value(concept_facts.get("interest_expense_only", []), period_end)
        if direct is not None:
            return direct
        costs = cls._duration_value(concept_facts.get("finance_costs_only", []), period_end)
        if costs is None:
            return cls._duration_value(concept_facts["interest_expense"], period_end)
        income = cls._duration_value(concept_facts.get("finance_income", []), period_end)
        net = cls._duration_value(concept_facts.get("net_finance_cost", []), period_end)
        # Only an extreme gross-up (income nearly cancels the costs and the
        # issuer's own net line is <= 1/8 of gross) replaces the gross figure.
        if income is None or net is None or costs <= 0 or income < 0.8 * costs or abs(net) * 8 > costs:
            return costs
        return abs(net) if net < 0 else None


    @classmethod
    def _excluded_candidates(
        cls, facts: list[dict], period_end: date, *, need_ebitda: bool, need_capex: bool
    ) -> dict[str, float]:
        """Tagged lines that look like missing EBITDA/FCF inputs but are *not*
        accepted by policy (impairment-inclusive D&A, generic investing outflows).

        They are reported, never used: this lets an audit tell a genuinely
        absent field from a field the filing tags in a non-standard way.
        """
        patterns: list[str] = []
        if need_ebitda:
            patterns += ["depreciationamortisationandimpairment", "depreciationandamortisationexpenseandimpairment"]
        if need_capex:
            patterns += ["purchaseofotherlongtermassets", "capitalexpenditure", "purchaseofintangibleassets"]
        if not patterns:
            return {}
        by_concept: dict[str, list[dict]] = {}
        for fact in facts:
            dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
            concept = str(dims.get("concept") or "")
            if any(key in concept.lower() for key in patterns) and not any(
                k not in {"concept", "entity", "period", "unit"} for k in dims
            ):
                by_concept.setdefault(concept, []).append(fact)
        found: dict[str, float] = {}
        for concept, rows in by_concept.items():
            value = cls._duration_value(rows, period_end)
            if value is not None:
                found[concept] = value
        return found

    @staticmethod
    def _duration_value(facts: list[dict], period_end: date, *, previous: bool = False) -> Optional[float]:
        candidates: list[tuple[int, date, float]] = []
        for fact in facts:
            dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
            start, end = _period_parts(dims.get("period"))
            value = _num(fact.get("value"))
            if start is None or end is None or value is None or end <= start:
                continue
            duration = (end - start).days
            if 300 <= duration <= 400:
                candidates.append((duration, end, value))
        unique_by_end: dict[date, tuple[int, date, float]] = {}
        for row in candidates:
            old = unique_by_end.get(row[1])
            if old is None or abs(row[0] - 365) < abs(old[0] - 365):
                unique_by_end[row[1]] = row
        # Flows are anchored to the balance-sheet date like instants are: a
        # short (transition) period ending on period_end must not be filled
        # with the prior fiscal year's annual flows (Mediobanca FY2025 is
        # 2025-07-01..2025-12-31; its last annual P&L ends 2025-06-30).
        target = period_end - timedelta(days=365) if previous else period_end
        tolerance = 10 if previous else 7
        near = [row for row in unique_by_end.values() if abs((row[1] - target).days) <= tolerance]
        near.sort(key=lambda row: abs((row[1] - target).days))
        return near[0][2] if near else None

    @classmethod
    def _distinct_concept_durations(cls, facts: list[dict], period_end: date) -> dict[str, float]:
        """One annual value per distinct concept (no double counting of a line
        tagged twice in the same filing)."""
        by_concept: dict[str, list[dict]] = {}
        for fact in facts:
            dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
            by_concept.setdefault(str(dims.get("concept") or ""), []).append(fact)
        values = {}
        for concept, rows in by_concept.items():
            value = cls._duration_value(rows, period_end)
            if value is not None:
                values[concept] = value
        return values

    @staticmethod
    def _instant_value(facts: list[dict], period_end: date) -> Optional[float]:
        choices: list[tuple[int, float]] = []
        for fact in facts:
            dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
            start, end = _period_parts(dims.get("period"))
            value = _num(fact.get("value"))
            if end is None or value is None or start != end:
                continue
            distance = abs((period_end - end).days)
            if distance <= 7:
                choices.append((distance, value))
        choices.sort(key=lambda item: item[0])
        return choices[0][1] if choices else None

    @staticmethod
    def _is_concept(concept: str, key: str) -> bool:
        return concept.lower() in {c.lower() for c in _CONCEPTS[key]} or _extension_key(concept) == key

    @classmethod
    def _owners_equity_facts(cls, facts: list[dict]) -> list[dict]:
        """Owners' equity totals: plain facts, or the single IFRS owners-total
        column of the statement of changes in equity (no other dimension)."""
        return cls._column_facts(facts, "owners_equity", _OWNERS_TOTAL_DIMENSION, plain=True)

    @classmethod
    def _column_facts(cls, facts: list[dict], key: str, column: tuple[str, str], *, plain: bool) -> list[dict]:
        axis, member = column
        result = []
        for fact in facts:
            dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
            if not cls._is_concept(str(dims.get("concept") or ""), key) or _num(fact.get("value")) is None:
                continue
            extra = {k: v for k, v in dims.items() if k not in _ALLOWED_DIMENSIONS}
            if (plain and not extra) or extra == {axis: member}:
                result.append(fact)
        return result

    def _equity(self, facts: list[dict], concept_facts: dict, period_end: date) -> tuple[Optional[float], Optional[str]]:
        direct = [f for f in concept_facts["equity"] if str(f["dimensions"].get("concept") or "").lower() == "ifrs-full:equity"]
        value = self._instant_value(direct, period_end)
        if value is not None:
            return value, "direct_ifrs_equity"
        bound = self._instant_value(concept_facts["equity_and_liabilities"], period_end)

        def plausible(amount: Optional[float]) -> bool:
            return amount is not None and (bound is None or abs(amount) <= abs(bound))

        value = self._instant_value([f for f in concept_facts["equity"] if f not in direct], period_end)
        if plausible(value):
            return value, "issuer_extension_total_equity"
        owners = self._instant_value(self._owners_equity_facts(facts), period_end)
        if owners is None:
            owners = self._instant_value(self._column_facts(facts, "equity", _OWNERS_TOTAL_DIMENSION, plain=False), period_end)
        minority = self._instant_value(concept_facts["noncontrolling_interests"], period_end)
        if minority is None:
            minority = self._instant_value(self._column_facts(facts, "equity", _NCI_DIMENSION, plain=False), period_end)
        if owners is not None and minority is not None and plausible(owners + minority):
            return owners + minority, "owners_equity_plus_noncontrolling_interests"
        cross_footed = self._cross_footed_equity(facts, concept_facts, period_end)
        if plausible(cross_footed):
            return cross_footed, "extension_components_cross_footed"
        return None, None

    def _cross_footed_equity(self, facts: list[dict], concept_facts: dict, period_end: date) -> Optional[float]:
        """Total equity from a statement-of-changes-in-equity column set that proves itself.

        Some issuers (FinecoBank) tag the closing owners' total only with a
        ``PreviouslyStated`` restatement member and no plain total. That total is
        accepted only when nothing contradicts it and the columns reconcile:
        no restated column exists at that date, the component columns sum to the
        owners' total, one component equals the income statement's profit, and
        non-controlling interests are tagged explicitly.
        """
        nearest: Optional[int] = None
        columns: list[tuple[str, Optional[str], float]] = []
        for fact in facts:
            dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
            concept = str(dims.get("concept") or "")
            member = dims.get(_COMPONENTS_AXIS)
            value = _num(fact.get("value"))
            if member is None or value is None or not (
                self._is_concept(concept, "owners_equity") or self._is_concept(concept, "equity")
            ):
                continue
            if set(dims) - _ALLOWED_DIMENSIONS - {_COMPONENTS_AXIS, _RESTATEMENT_AXIS}:
                continue
            start, end = _period_parts(dims.get("period"))
            if end is None or start != end or abs((period_end - end).days) > 7:
                continue
            distance = abs((period_end - end).days)
            if nearest is None or distance < nearest:
                nearest, columns = distance, []
            if distance == nearest:
                columns.append((str(member), dims.get(_RESTATEMENT_AXIS), value))
        if not columns or any(axis not in (None, _PREVIOUSLY_STATED) for _, axis, _ in columns):
            return None
        by_member: dict[str, float] = {}
        for member, _, value in columns:
            if by_member.setdefault(member, value) != value:
                return None
        owners = by_member.get("ifrs-full:EquityAttributableToOwnersOfParentMember")
        minority = by_member.get("ifrs-full:NoncontrollingInterestsMember")
        components = [v for m, v in by_member.items() if m.lower() not in _EQUITY_TOTAL_MEMBERS]
        if owners is None or minority is None or len(components) < 3:
            return None
        tolerance = max(1e-4 * abs(owners), 1000.0 * len(components))
        if abs(sum(components) - owners) > tolerance:
            return None
        profit = self._duration_value(concept_facts["net_income"], period_end)
        if profit is None or not any(abs(v - profit) <= max(1e-4 * abs(profit), 1000.0) for v in components):
            return None
        return owners + minority

    def _revenue_from_operating_total(
        self, concept_facts: dict, period_end: date
    ) -> tuple[Optional[float], Optional[float], Optional[str]]:
        """Revenue from an issuer's tagged "revenue and operating income" total.

        Other income tagged for the same year is subtracted; a year whose
        total is tagged without any other-income line uses the total as-is.
        Both years are derived the same way so growth is like for like.
        """
        totals = concept_facts["revenue_and_operating_income"]
        other = concept_facts["other_operating_income"]
        current_total = self._duration_value(totals, period_end)
        if current_total is None:
            return None, None, None
        current_other = self._duration_value(other, period_end)
        netted = current_other is not None
        previous_total = self._duration_value(totals, period_end, previous=True)
        previous_other = self._duration_value(other, period_end, previous=True)
        revenue = current_total - current_other if netted else current_total
        if previous_total is None or netted != (previous_other is not None):
            revenue_prev = None
        else:
            revenue_prev = previous_total - previous_other if netted else previous_total
        if revenue <= 0:
            return None, None, None
        method = "revenue_and_operating_income_minus_other_income" if netted else "revenue_and_operating_income_total"
        return revenue, revenue_prev, method

    @staticmethod
    def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
        return None if current is None or previous in (None, 0) else (current / previous - 1.0) * 100.0

    @staticmethod
    def _margin(value: Optional[float], revenue: Optional[float]) -> Optional[float]:
        return None if value is None or revenue in (None, 0) else value / revenue * 100.0

    # A verified fiscal-year transition: the report's flows cover one short
    # period (5-8 months) ending on the balance-sheet date, immediately after a
    # 12-month fiscal year. Such figures are exposed separately and are never
    # annualized or placed in the annual fields that feed scoring models.
    TRANSITION_MIN_DAYS = 150
    TRANSITION_MAX_DAYS = 250

    @staticmethod
    def _window_flow(facts: list[dict], target_end: date, min_days: int, max_days: int, *, tolerance: int):
        """``(value, start, end)`` of the flow whose period ends at ``target_end`` and
        lasts ``min_days..max_days``; ``None`` when absent or ambiguous."""
        found: dict[tuple[date, date], set[float]] = {}
        for fact in facts:
            dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
            start, end = _period_parts(dims.get("period"))
            value = _num(fact.get("value"))
            if start is None or end is None or value is None or end <= start:
                continue
            if min_days <= (end - start).days <= max_days and abs((end - target_end).days) <= tolerance:
                found.setdefault((start, end), set()).add(value)
        if len(found) != 1:
            return None
        (start, end), values = next(iter(found.items()))
        return (next(iter(values)), start, end) if len(values) == 1 else None

    def fiscal_year_transition(self, facts: list[dict], period_end: date) -> Optional[dict]:
        """Verified transition-period figures, or ``None``.

        Verified means: no 12-month net income ends at ``period_end``; exactly
        one 5-8 month net income ends there; and a 12-month net income ends the
        day before that short period starts (the last annual year).
        """
        net = self._concept_facts(facts, _CONCEPTS["net_income"], extension_key="net_income")
        if self._duration_value(net, period_end) is not None:
            return None
        current = self._window_flow(net, period_end, self.TRANSITION_MIN_DAYS, self.TRANSITION_MAX_DAYS, tolerance=7)
        if current is None:
            return None
        _, start, end = current
        prior = self._window_flow(net, start - timedelta(days=1), 300, 400, tolerance=5)
        if prior is None:
            return None
        days = (end - start).days + 1
        figures: dict[str, Optional[float]] = {}
        for key, name in (("net_income", "net_income"), ("ocf", "operating_cash_flow"), ("bank_operating_income", "bank_operating_income")):
            rows = self._concept_facts(facts, _CONCEPTS[key], extension_key=key)
            hit = self._window_flow(rows, end, self.TRANSITION_MIN_DAYS, self.TRANSITION_MAX_DAYS, tolerance=7)
            if hit is not None and hit[1] == start:
                figures[name] = hit[0]
        return {
            "status": "VERIFIED_TRANSITION_PERIOD",
            "periodLabel": f"{start.isoformat()}..{end.isoformat()} ({round(days / 30.4)}-month fiscal-year transition period)",
            "periodStart": start.isoformat(),
            "periodEnd": end.isoformat(),
            "months": round(days / 30.4),
            "days": days,
            "balanceSheetDate": period_end.isoformat(),
            "figures": figures,
            "priorAnnualPeriod": {"start": prior[1].isoformat(), "end": prior[2].isoformat(), "netIncome": prior[0]},
            "annualizable": False,
            "usedForAnnualScoring": False,
            "annualScoringStatus": "BLOCK_NO_12_MONTH_INCOME_STATEMENT",
            "method": "same-filing IFRS facts; short period only; never annualized",
        }

    @classmethod
    def _single_class_shares_issued(cls, facts: list[dict], period_end: date) -> tuple[Optional[float], Optional[str]]:
        """Issued share count for a verified single-class issuer, else (None, None).

        Accepted only when every check holds; any doubt withholds the count so
        market cap stays missing rather than guessed:
        * one plain (undimensioned) ``NumberOfSharesIssued`` instant fact within
          7 days of the balance-sheet date, in a share unit, positive, and all
          such facts agree;
        * no dimensioned (per-class / per-component) issued or outstanding
          share fact exists at that date, i.e. the filing tags no share classes.
        """
        wanted = {"ifrs-full:numberofsharesissued", "ifrs-full:numberofsharesoutstanding"}
        plain: list[float] = []
        for fact in facts:
            dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
            if str(dims.get("concept") or "").lower() not in wanted:
                continue
            start, end = _period_parts(dims.get("period"))
            if end is None or start != end or abs((period_end - end).days) > 7:
                continue
            if not cls._plain_fact(fact):
                return None, None  # per-class facts present: multi-class or unclear
            if str(dims.get("concept") or "").lower() != "ifrs-full:numberofsharesissued":
                continue
            value = _num(fact.get("value"))
            unit = str(dims.get("unit") or "").lower()
            if value is None or value <= 0 or "shares" not in unit:
                return None, None
            plain.append(value)
        if not plain or len(set(plain)) != 1:
            return None, None
        return plain[0], "issued_single_class_fallback"

    _IMPAIRMENT_INCLUSIVE_DA = re.compile(r"(depreciation|amortisation|amortization).*impairment|adjustmentsfordepreciationandamortisation", re.I)
    _BORROWING_NAME = re.compile(r"(borrowing|bondsissued|loansreceived)", re.I)

    @classmethod
    def _field_status(
        cls, facts: list[dict], period_end: date, *, shares: Optional[float], shares_basis: Optional[str],
        operating_income: Optional[float], ebitda: Optional[float], debt: Optional[float], debt_method: Optional[str],
    ) -> dict[str, str]:
        """Why each valuation/credit input is present or absent.

        ``not_tagged_*`` means the official structured filing genuinely does not
        carry the value; ``tagged_*`` means it carries something we deliberately
        did not use (the reason is named), i.e. an extraction decision, not a
        data gap.
        """
        near_period = []
        for fact in facts:
            dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
            _, end = _period_parts(dims.get("period"))
            if end is not None and abs((period_end - end).days) <= 7:
                near_period.append((str(dims.get("concept") or ""), cls._plain_fact(fact)))

        def local(concept: str) -> str:
            return concept.split(":")[-1]

        if shares is not None:
            shares_status = "extracted_issued_single_class_fallback" if shares_basis else "extracted_plain_outstanding"
        elif any(local(c).lower() in {"numberofsharesoutstanding", "numberofsharesissued"} for c, _ in near_period):
            shares_status = "tagged_per_class_or_ambiguous_not_summed"
        elif any(re.search(r"numberof.*shares|shares.*(outstanding|issued)", local(c), re.I) for c, _ in near_period):
            shares_status = "tagged_issuer_extension_concept_not_mapped"
        else:
            shares_status = "not_tagged_in_filing"

        if ebitda is not None:
            ebitda_status = "extracted"
        elif operating_income is None:
            ebitda_status = "operating_income_not_tagged"
        elif any(cls._IMPAIRMENT_INCLUSIVE_DA.search(local(c)) for c, _ in near_period):
            ebitda_status = "tagged_da_impairment_inclusive_only_not_used"
        else:
            ebitda_status = "not_tagged_depreciation_amortisation"

        if debt is not None:
            debt_status = "extracted"
        elif str(debt_method or "").startswith("withheld:"):
            debt_status = "tagged_components_inconsistent_withheld"
        elif any(cls._BORROWING_NAME.search(local(c)) and c.lower().startswith("ifrs-full:") and not re.search(r"(proceeds|repayment|cashflows)", local(c), re.I) for c, _ in near_period):
            debt_status = "tagged_borrowing_lines_incomplete_not_used"
        else:
            debt_status = "not_tagged_borrowings"
        return {"shares_outstanding": shares_status, "ebitda": ebitda_status, "total_debt": debt_status}

    def normalized_fields(self, facts: list[dict], period_end: date) -> dict:
        """Map plain annual IFRS facts to GlobalCompany fields.

        Shared by every ESEF transport (xbrl.org index JSON and national OAM
        inline-XBRL packages) so one extraction contract applies to all
        European markets. Missing concepts stay None.
        """
        concept_facts = {
            key: self._concept_facts(facts, concepts, extension_key=key)
            for key, concepts in _CONCEPTS.items()
        }
        revenue = self._duration_value(concept_facts["revenue"], period_end)
        revenue_prev = self._duration_value(concept_facts["revenue"], period_end, previous=True)
        revenue_method = "ifrs_revenue" if revenue is not None else None
        # Banks tag no IFRS Revenue; their top line is the tagged item 120
        # subtotal. Used only for a bank-structured filing (fee/commission
        # result and effective-interest revenue both tagged for the year).
        if (
            revenue is None
            and self._duration_value(concept_facts["bank_fee_income"], period_end) is not None
            and self._duration_value(concept_facts["bank_interest_revenue"], period_end) is not None
        ):
            revenue = self._duration_value(concept_facts["bank_operating_income"], period_end)
            if revenue is not None:
                revenue_prev = self._duration_value(concept_facts["bank_operating_income"], period_end, previous=True)
                revenue_method = "bank_net_interest_and_other_banking_income"
        if (
            revenue is None
            and self._duration_value(concept_facts["revenue_rendering_of_services"], period_end) is None
        ):
            revenue = self._duration_value(concept_facts["revenue_sale_of_goods"], period_end)
            if revenue is not None:
                revenue_prev = self._duration_value(concept_facts["revenue_sale_of_goods"], period_end, previous=True)
                revenue_method = "revenue_from_sale_of_goods_only_revenue_line"
        if revenue is None:
            derived = self._revenue_from_operating_total(concept_facts, period_end)
            if derived[0] is not None:
                revenue, revenue_prev, revenue_method = derived
        total_equity, equity_method = self._equity(facts, concept_facts, period_end)
        total_assets = self._instant_value(concept_facts["assets"], period_end)
        total_liabilities = self._instant_value(concept_facts["liabilities"], period_end)
        liabilities_method = "direct_ifrs_liabilities" if total_liabilities is not None else None
        if (
            total_liabilities is not None
            and total_assets
            and total_equity is not None
            and total_assets > 0
            and 0.001 * total_assets < total_equity <= total_assets
            and abs(total_liabilities - total_assets) <= 0.0005 * total_assets
        ):
            # Some filers (e.g. S30, NRG, PAT, GAB) tag the "total equity and
            # liabilities" line with ifrs-full:Liabilities. Liabilities equal to
            # total assets next to positive equity violates the balance sheet
            # and would inflate Zmijewski TL/TA to 1.0 in Agent 9. Same filing,
            # same period: use the identity; never estimate.
            total_liabilities = total_assets - total_equity
            liabilities_method = "derived_assets_minus_equity_direct_liabilities_tag_equalled_total_assets"
        # The balance-sheet identity is valid only for the same consolidated
        # entity, reporting currency and balance-sheet date. This normalizer
        # has already selected the filing's matching period and unit.
        if total_liabilities is None and total_assets is not None and total_equity is not None:
            derived_liabilities = total_assets - total_equity
            if derived_liabilities >= 0 and total_equity <= total_assets:
                total_liabilities = derived_liabilities
                liabilities_method = "derived_assets_minus_equity_same_filing_period"
        if total_liabilities is None and total_assets is None and total_equity is not None:
            # Balance-sheet total "equity and liabilities" is the same identity
            # when the assets total itself is not tagged.
            balance_total = self._instant_value(concept_facts["equity_and_liabilities"], period_end)
            if balance_total is not None and 0 <= total_equity <= balance_total:
                total_liabilities = balance_total - total_equity
                liabilities_method = "derived_equity_and_liabilities_minus_equity_same_filing_period"
        retained_earnings = self._instant_value(concept_facts["retained_earnings"], period_end)
        retained_earnings_method = "direct_retained_earnings_tag" if retained_earnings is not None else None
        if retained_earnings is None:
            # Statement of changes in equity: closing balance of the IFRS
            # retained-earnings column (exactly one ComponentsOfEquityAxis
            # member, no other dimension), e.g. AB Volvo FY2025.
            column = [
                f for f in self._column_facts(facts, "equity", _RETAINED_EARNINGS_DIMENSION, plain=False)
                if str(f["dimensions"].get("concept") or "").lower() == "ifrs-full:equity"
            ]
            retained_earnings = self._instant_value(column, period_end)
            if retained_earnings is not None:
                retained_earnings_method = "equity_statement_retained_earnings_column"
        net_income = self._duration_value(concept_facts["net_income"], period_end)
        net_income_prev = self._duration_value(concept_facts["net_income"], period_end, previous=True)
        operating_income = self._duration_value(concept_facts["operating_income"], period_end)
        direct_ebitda = self._duration_value(concept_facts["ebitda"], period_end)
        depreciation_amortisation = self._duration_value(concept_facts["depreciation_amortisation"], period_end)
        da_method = "income_statement_da_total" if depreciation_amortisation is not None else None
        if depreciation_amortisation is None:
            depreciation_amortisation = self._duration_value(concept_facts["depreciation_amortisation_cash_flow"], period_end)
            if depreciation_amortisation is not None:
                da_method = "cash_flow_da_add_back"
        if depreciation_amortisation is None:
            # Distinct D&A lines (intangibles, PP&E, leased assets) tagged
            # separately with no total: sum one value per distinct concept.
            component_values = self._distinct_concept_durations(
                concept_facts["depreciation_amortisation_component"], period_end
            )
            if component_values:
                depreciation_amortisation = sum(abs(value) for value in component_values.values())
                da_method = "sum_of_tagged_da_components:" + ",".join(sorted(component_values))
        if depreciation_amortisation is None:
            # Reviewed issuer mapping (never guessed): extension-tagged PP&E and
            # intangible depreciation lines of one named issuer, summed.
            for lei in {
                str((fact.get("dimensions") or {}).get("entity") or "").split(":")[-1].upper() for fact in facts
            }:
                reviewed_da = _reviewed_da_lines().get(lei)
                if not reviewed_da:
                    continue
                parts_da = [
                    self._duration_value(self._concept_facts(facts, (str(concept),)), period_end)
                    for concept in reviewed_da["concepts"]
                ]
                if parts_da and all(value is not None for value in parts_da):
                    depreciation_amortisation = sum(abs(value) for value in parts_da)
                    da_method = "reviewed_issuer_da_lines:" + ",".join(c.split(":")[-1] for c in reviewed_da["concepts"])
                    break
        ebitda = direct_ebitda
        ebitda_method = "direct_explicit_tag" if direct_ebitda is not None else None
        if ebitda is None and operating_income is not None and depreciation_amortisation is not None:
            ebitda = operating_income + abs(depreciation_amortisation)
            ebitda_method = "derived_operating_income_plus_abs_depreciation_amortisation"
        ocf = self._duration_value(concept_facts["ocf"], period_end)
        capex = self._duration_value(concept_facts["capex"], period_end)
        capex_method = "standard_ppe_capex_concept" if capex is not None else None
        if capex is None:
            # Reviewed issuer mapping (never guessed): the issuer's own statement line
            # "Capital expenditure" carries a generic IFRS concept the policy does not
            # accept for other issuers.
            entities = {
                str((fact.get("dimensions") or {}).get("entity") or "").split(":")[-1].upper()
                for fact in facts
            }
            for lei in entities:
                reviewed = _reviewed_capex_lines().get(lei)
                if not reviewed:
                    continue
                capex = self._duration_value(
                    self._concept_facts(facts, (str(reviewed["concept"]),)), period_end
                )
                if capex is not None:
                    capex_method = f"reviewed_statement_line:{reviewed['concept']}"
                    break
        fcf = None if ocf is None or capex is None else ocf - abs(capex)
        debt = self._instant_value(concept_facts["borrowings"], period_end)
        debt_method = "direct_borrowings" if debt is not None else None
        if debt is None:
            parts = [
                self._instant_value(concept_facts["current_borrowings"], period_end),
                self._instant_value(concept_facts["noncurrent_borrowings"], period_end),
            ]
            present = [value for value in parts if value is not None]
            debt = sum(present) if present else None
            if debt is not None:
                debt_method = "current_plus_noncurrent_borrowings"
                # A single bond/loan balance larger than the claimed total means the
                # tagged borrowings line is a sub-aggregate (Stillfront FY2025:
                # LongtermBorrowings 984m next to bonds 2,835m). Withhold, never guess.
                components = [
                    self._instant_value(concept_facts[key], period_end)
                    for key in ("current_bonds", "noncurrent_bonds", "current_other_loans", "noncurrent_other_loans")
                ]
                if any(value is not None and abs(value) > debt * 1.0001 for value in components):
                    debt = None
                    debt_method = "withheld:component_exceeds_borrowings_total"
        if debt is None and debt_method is None:
            # No borrowings line at all: bonds issued plus issuer "other loans"
            # are the interest-bearing debt lines of the balance sheet.
            lines = {
                key: self._instant_value(concept_facts[key], period_end)
                for key in ("current_bonds", "noncurrent_bonds", "current_other_loans", "noncurrent_other_loans")
            }
            present_lines = {key: value for key, value in lines.items() if value is not None}
            if any(key.endswith("bonds") for key in present_lines):
                candidate = sum(abs(value) for value in present_lines.values())
                if total_liabilities is None or candidate <= total_liabilities:
                    debt = candidate
                    debt_method = "sum_of_bonds_and_loans:" + ",".join(sorted(present_lines))
        ffo = None
        ffo_method = None
        interest_paid = self._duration_value(concept_facts["interest_paid"], period_end)
        taxes_paid = self._duration_value(concept_facts["income_taxes_paid"], period_end)
        if ebitda is not None and interest_paid is not None and taxes_paid is not None:
            interest_received = self._duration_value(concept_facts["interest_received"], period_end)
            ffo = ebitda - abs(interest_paid) + abs(interest_received or 0.0) - taxes_paid
            ffo_method = (
                "ebitda_minus_interest_paid_plus_interest_received_minus_income_taxes_paid"
                if interest_received is not None
                else "ebitda_minus_interest_paid_minus_income_taxes_paid"
            )

        eps = self._duration_value(concept_facts["eps"], period_end)
        if eps is None and not self._duration_value(concept_facts["discontinued_profit"], period_end):
            eps = self._duration_value(concept_facts["eps_continuing"], period_end)

        shares_outstanding = self._instant_value(concept_facts["shares_outstanding"], period_end)
        if shares_outstanding is not None and shares_outstanding <= 0:
            shares_outstanding = None
        shares_basis = None
        if shares_outstanding is None:
            shares_outstanding, shares_basis = self._single_class_shares_issued(facts, period_end)

        reporting_currency = None
        for key in ("revenue", "net_income", "assets"):
            for fact in concept_facts.get(key, []):
                dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
                reporting_currency = _unit_currency(dims.get("unit"))
                if reporting_currency:
                    break
            if reporting_currency:
                break

        return {
            "reporting_currency": reporting_currency,
            "revenue": revenue,
            "revenue_prev": revenue_prev,
            "revenue_yoy_pct": self._pct_change(revenue, revenue_prev),
            "gross_profit": self._duration_value(concept_facts["gross_profit"], period_end),
            "operating_income": operating_income,
            "ebitda": ebitda,
            "net_income": net_income,
            "net_margin_pct": self._margin(net_income, revenue),
            "net_margin_prev_pct": self._margin(net_income_prev, revenue_prev),
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
            "retained_earnings": retained_earnings,
            "current_assets": self._instant_value(concept_facts["current_assets"], period_end),
            "current_liabilities": self._instant_value(concept_facts["current_liabilities"], period_end),
            "cash_and_equivalents": self._instant_value(concept_facts["cash"], period_end),
            "operating_cash_flow": ocf,
            "free_cash_flow": fcf,
            "total_debt": debt,
            "interest_expense": self._interest_expense(concept_facts, period_end),
            "eps": eps,
            # absent key (not None) when the filing carries no plain share count,
            # so an existing provider value is never overwritten with a gap
            **({"shares_outstanding": shares_outstanding} if shares_outstanding is not None else {}),
            "__normalization_meta__": {
                **({"shares_outstanding_basis": shares_basis} if shares_basis else {}),
                "field_status": self._field_status(
                    facts, period_end,
                    shares=shares_outstanding, shares_basis=shares_basis,
                    operating_income=operating_income, ebitda=ebitda,
                    debt=debt, debt_method=debt_method,
                ),
                "revenue_method": revenue_method,
                "equity_method": equity_method,
                "liabilities_method": liabilities_method,
                "retained_earnings_method": retained_earnings_method,
                "ebitda_method": ebitda_method,
                "net_income_attributable_to_owners": self._duration_value(
                    concept_facts["net_income_owners"], period_end
                ),
                "depreciation_amortisation": depreciation_amortisation,
                "depreciation_amortisation_method": da_method,
                "debt_method": debt_method,
                "capex": capex,
                "fcf_method": "operating_cash_flow_minus_abs_capex" if fcf is not None else None,
                "capex_method": capex_method,
                "fiscal_year_transition": self.fiscal_year_transition(facts, period_end),
                "ffo": ffo,
                "ffo_method": ffo_method,
                "excluded_candidates": self._excluded_candidates(
                    facts, period_end, need_ebitda=ebitda is None, need_capex=fcf is None
                ),
            },
        }

    def anchor_period(self, facts: list[dict], indexed: date) -> tuple[date, bool]:
        """The balance-sheet date the filing's own facts report, when the index is wrong.

        filings.xbrl.org sometimes indexes a report under its filing/signing date
        (Aviva FY2025 is listed as 2026-03-02, Mobico as 2026-03-31) although the
        facts end 2025-12-31; every anchored lookup then misses and the issuer
        shows no core figures. The index date is kept whenever any annual flow
        ends within a week of it. Otherwise the latest annual-flow end up to 200
        days before the index date is used, but only if a balance-sheet instant
        sits on that same date, so the figures are the filing's own and cross-foot
        on one date. Staleness is then measured from the true period end.
        """
        flow_keys = ("net_income", "revenue", "operating_income")
        ends: set[date] = set()
        any_flow_ends: set[date] = set()
        for key in flow_keys:
            for fact in self._concept_facts(facts, _CONCEPTS[key], extension_key=key):
                dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
                start, end = _period_parts(dims.get("period"))
                if start is None or end is None or end <= start:
                    continue
                any_flow_ends.add(end)
                if 300 <= (end - start).days <= 400:
                    ends.add(end)
        # A flow of ANY length ending at the index date means the index is right
        # (transition-period and 15-month filers keep their own handling).
        if any(abs((end - indexed).days) <= 7 for end in any_flow_ends):
            return indexed, False
        assets = self._concept_facts(facts, _CONCEPTS["assets"], extension_key="assets")
        for end in sorted((e for e in ends if 0 < (indexed - e).days <= 200), reverse=True):
            if self._instant_value(assets, end) is not None:
                return end, True
        return indexed, False

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        lei, legal_name = self._resolve_lei(company)
        filing = self._latest_filing(lei, company.country)
        attrs = filing.get("attributes") if isinstance(filing.get("attributes"), dict) else {}
        period_text = str(attrs.get("period_end") or "")[:10]
        try:
            period_end = date.fromisoformat(period_text)
        except ValueError as exc:
            raise GlobalProviderError(f"invalid ESEF period end {period_text!r}") from exc
        json_url = str(attrs.get("json_url") or "").strip()
        if json_url.startswith("/"):
            json_url = "https://filings.xbrl.org" + json_url
        xbrl = self._get_json(json_url)
        facts = self._facts(xbrl)
        if not facts:
            raise GlobalProviderError(f"ESEF xBRL-JSON contains no facts for LEI {lei}")

        indexed_period = period_end
        period_end, period_corrected = self.anchor_period(facts, period_end)
        normalized = self.normalized_fields(facts, period_end)
        reporting_currency = normalized.pop("reporting_currency")
        normalization_meta = normalized.pop("__normalization_meta__", {})
        transition = normalization_meta.pop("fiscal_year_transition", None)

        try:
            errors = int(attrs.get("error_count") or 0)
        except (TypeError, ValueError):
            errors = 999
        try:
            inconsistencies = int(attrs.get("inconsistency_count") or 0)
        except (TypeError, ValueError):
            inconsistencies = 999
        quality = 0.96 if errors == 0 and inconsistencies == 0 else 0.86 if errors <= 5 else 0.72
        processed = str(attrs.get("processed") or attrs.get("date_added") or "").strip() or None
        filing_id = str(filing.get("id") or attrs.get("fxo_id") or lei)
        viewer_url = str(attrs.get("viewer_url") or attrs.get("report_url") or json_url).strip()
        if viewer_url.startswith("/"):
            viewer_url = "https://filings.xbrl.org" + viewer_url

        enriched = replace(
            company,
            name=legal_name or company.name,
            lei=lei,
            reporting_currency=reporting_currency or company.reporting_currency,
            **normalized,
            filing_period_end=period_end.isoformat(),
            filing_observed_at=processed,
            report_scope=None,
            raw_provider_fields={
                **company.raw_provider_fields,
                "esef_filing_id": filing_id,
                "esef_validation_errors": errors,
                "esef_validation_inconsistencies": inconsistencies,
                "esef_json_url": json_url,
                "esef_credit_extraction": normalization_meta,
                **({"esef_index_period_end": indexed_period.isoformat(), "esef_period_end_source": "filing_facts"} if period_corrected else {}),
                **({"fiscal_year_transition": transition} if transition else {}),
                **_agent10_fields(normalization_meta),
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_regulatory_xbrl",
            source_id=filing_id,
            source_url=viewer_url,
            observed_at=processed,
            period_end=period_end.isoformat(),
            quality=quality,
            notes=(
                f"ESEF/UKSEF xBRL-JSON indexed by filings.xbrl.org; LEI={lei}; validationErrors={errors}; inconsistencies={inconsistencies}"
                + (f"; index period {indexed_period.isoformat()} does not match the filing's facts, period taken from the facts" if period_corrected else "")
            ),
        ))
