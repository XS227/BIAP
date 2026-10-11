"""SEC EDGAR/XBRL fundamentals adapter for BIAP Global US instruments.

Uses SEC public ticker mapping and `data.sec.gov/api/xbrl/companyfacts`. No API
key is required, but responsible automated access must identify the caller via
`BIAP_SEC_USER_AGENT`. Only explicit standard US-GAAP facts are normalized;
missing or ambiguous values remain unavailable.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import os
import threading
from typing import Any, Optional

import httpx

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source
from .sec_filing_instance import SECFilingInstanceReader, merge_facts

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_FACTS_BASE = "https://data.sec.gov/api/xbrl/companyfacts"
SEC_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
# Standard US-GAAP D&A concepts, most complete first. `Depreciation` alone
# (Tesla) excludes separately reported amortization/impairment, so an EBITDA
# built from it is a lower bound and is labelled as such.
DNA_TAGS_COMPLETE = ("DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet")
DNA_TAGS_PARTIAL = ("Depreciation",)
# SIC division ranges -> broad sector; peers are only compared inside one sector.
_SIC_SECTORS = (
    (100, 999, "Agriculture"), (1000, 1499, "Mining & Energy"), (1500, 1799, "Construction"),
    (2000, 2399, "Consumer Staples"), (2400, 2799, "Materials & Paper"), (2800, 2829, "Chemicals"),
    (2830, 2836, "Health Care"), (2837, 2899, "Chemicals"), (2900, 2999, "Mining & Energy"),
    (3000, 3499, "Industrials"), (3500, 3569, "Industrials"), (3570, 3579, "Technology"),
    (3580, 3599, "Industrials"), (3600, 3699, "Technology"), (3700, 3799, "Consumer Discretionary"),
    (3800, 3829, "Technology"), (3840, 3851, "Health Care"), (3852, 3999, "Industrials"),
    (4000, 4799, "Transportation"), (4800, 4899, "Communication Services"), (4900, 4999, "Utilities"),
    (5000, 5199, "Wholesale Trade"), (5200, 5999, "Retail"), (6000, 6799, "Financials"),
    (7000, 7299, "Consumer Services"), (7370, 7379, "Technology"), (7300, 8099, "Business & Health Services"),
    (8100, 8999, "Services"),
)


def sector_from_sic(sic: Any) -> Optional[str]:
    try:
        code = int(sic)
    except (TypeError, ValueError):
        return None
    # Later, narrower ranges win (7370-7379 inside 7300-8099).
    hit = None
    for lo, hi, name in _SIC_SECTORS:
        if lo <= code <= hi and (hit is None or (hi - lo) < hit[0]):
            hit = (hi - lo, name)
    return hit[1] if hit else None
# Successor registrants under Exchange Act Rule 12g-3(a) take over the listed
# ticker but have no annual facts until their first 10-K. Until then the
# predecessor's audited 10-K (same consolidated group) is the latest annual
# official filing. Each pair is reviewed against the reorganization 8-K.
VERIFIED_PREDECESSOR_CIKS = {
    # ExxonMobil Holdings Corp <- Exxon Mobil Corp: redomiciliation merger;
    # predecessor 8-K 0001193125-26-291986 and successor 8-K12B
    # 0001193125-26-291990 (both 2026-07-01), successor registrant per 12g-3(a).
    2115436: 34088,
}
# Companyfacts can lag a filed 10-K (BTBD FY2025: filed 2026-03-30, no 10-K
# facts months later). Only look for a newer filed instance when the newest
# annual period is older than this many days.
COMPANYFACTS_LAG_CHECK_DAYS = 365
_ticker_lock = threading.Lock()
_ticker_cache: Optional[dict[str, int]] = None


class SECEdgarFundamentalsProvider(FundamentalsProvider):
    provider_id = "sec-edgar-xbrl"

    def __init__(self, *, user_agent: Optional[str] = None, timeout: float = 15.0) -> None:
        self.user_agent = (user_agent or os.environ.get("BIAP_SEC_USER_AGENT") or "").strip()
        self.timeout = max(3.0, float(timeout))
        if not self.user_agent:
            raise GlobalProviderError("BIAP_SEC_USER_AGENT is required for responsible SEC automated access")

    def _get_json(self, url: str) -> dict:
        try:
            with httpx.Client(timeout=self.timeout, headers={"User-Agent": self.user_agent, "Accept": "application/json"}) as client:
                response = client.get(url)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"SEC request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError("unexpected SEC JSON response")
        return payload

    def _sic(self, cik: int) -> tuple[Optional[int], Optional[str]]:
        """SIC code/description from SEC submissions; sector is best-effort metadata."""
        try:
            data = self._get_json(f"{SEC_SUBMISSIONS_BASE}/CIK{cik:010d}.json")
            return int(data.get("sic")), str(data.get("sicDescription") or "") or None
        except (GlobalProviderError, TypeError, ValueError):
            return None, None

    def _ticker_map(self) -> dict[str, int]:
        global _ticker_cache
        if _ticker_cache is not None:
            return _ticker_cache
        with _ticker_lock:
            if _ticker_cache is not None:
                return _ticker_cache
            payload = self._get_json(SEC_TICKERS_URL)
            mapping: dict[str, int] = {}
            for row in payload.values():
                if not isinstance(row, dict):
                    continue
                ticker = str(row.get("ticker") or "").strip().upper()
                try:
                    cik = int(row.get("cik_str"))
                except (TypeError, ValueError):
                    continue
                if ticker:
                    mapping[ticker] = cik
            if not mapping:
                raise GlobalProviderError("SEC ticker mapping returned no usable rows")
            _ticker_cache = mapping
            return mapping

    def _resolve_cik(self, company: GlobalCompany) -> int:
        explicit = company.raw_provider_fields.get("sec_cik")
        if explicit not in (None, ""):
            try:
                return int(explicit)
            except (TypeError, ValueError) as exc:
                raise GlobalProviderError(f"invalid SEC CIK for {company.identity()}") from exc
        ticker = company.ticker.strip().upper()
        mapping = self._ticker_map()
        # SEC lists share classes with a hyphen (TAP-A, BRK-B); exchanges use a dot.
        # Only the exact ticker or its dot->hyphen form is tried, never a prefix guess.
        cik = mapping.get(ticker)
        if cik is None and "." in ticker:
            cik = mapping.get(ticker.replace(".", "-"))
        if cik is None:
            raise GlobalProviderError(f"SEC CIK not found for ticker {company.ticker.strip().upper()}")
        return cik

    @staticmethod
    def _facts(payload: dict) -> dict:
        facts = payload.get("facts")
        if not isinstance(facts, dict):
            return {}
        gaap = facts.get("us-gaap")
        return gaap if isinstance(gaap, dict) else {}

    @staticmethod
    def _annual_rows(concept: dict) -> list[dict]:
        units = concept.get("units") if isinstance(concept, dict) else None
        if not isinstance(units, dict):
            return []
        rows: list[dict] = []
        for entries in units.values():
            if not isinstance(entries, list):
                continue
            for row in entries:
                if not isinstance(row, dict) or not isinstance(row.get("val"), (int, float)):
                    continue
                form = str(row.get("form") or "").upper()
                fp = row.get("fp")
                if form in {"10-K", "10-K/A", "20-F", "20-F/A"}:
                    # Foreign private issuers can file Form 20-F while still
                    # preparing the financial statements under US GAAP (for
                    # example PC, PASW and ODD on Nasdaq). Companyfacts already
                    # separates the US-GAAP namespace, so annual 20-F facts are
                    # safe to consume here alongside domestic 10-K facts.
                    if fp not in {None, "FY"}:
                        continue
                elif form in {"10-12B", "10-12B/A", "10-12G", "10-12G/A"}:
                    # Newly public issuers may not have filed their first 10-K yet.
                    # Accept only explicit fiscal-year facts from the audited
                    # Exchange Act registration statement; never interim rows.
                    if fp != "FY":
                        continue
                else:
                    continue
                rows.append(row)
        rows.sort(key=lambda row: (str(row.get("end") or ""), str(row.get("filed") or "")), reverse=True)
        return rows

    @classmethod
    def _annual_series(cls, gaap: dict, tags: tuple[str, ...], count: int = 2) -> list[dict]:
        # Issuers sometimes migrate between standard US-GAAP tags. Prefer the
        # candidate series whose newest annual fact is actually most recent;
        # tag order is only a tie-breaker, never a reason to select stale data.
        best: list[dict] = []
        best_key: tuple[str, str] = ("", "")
        for tag in tags:
            concept = gaap.get(tag)
            if not isinstance(concept, dict):
                continue
            unique: list[dict] = []
            seen_periods: set[str] = set()
            for row in cls._annual_rows(concept):
                period = str(row.get("end") or row.get("fy") or "")
                if not period or period in seen_periods:
                    continue
                seen_periods.add(period)
                unique.append(row)
                if len(unique) >= count:
                    break
            if unique:
                key = (
                    str(unique[0].get("end") or ""),
                    str(unique[0].get("filed") or ""),
                )
                if key > best_key:
                    best = unique
                    best_key = key
        return best

    @classmethod
    def _has_annual_facts(cls, gaap: dict) -> bool:
        return any(cls._latest(gaap, (tag,)) for tag in ("NetIncomeLoss", "ProfitLoss", "Assets", "StockholdersEquity"))

    @classmethod
    def _latest(cls, gaap: dict, tags: tuple[str, ...]) -> Optional[dict]:
        rows = cls._annual_series(gaap, tags, count=1)
        return rows[0] if rows else None

    @classmethod
    def _consistent_equity(cls, gaap: dict, assets: Optional[dict], liabilities: Optional[dict]) -> Optional[dict]:
        """Total equity, cross-checked against the balance-sheet identity.

        The NCI-inclusive total is preferred, but filers occasionally tag an
        equity component with it (Agilent FY2025: accumulated OCI -226m under
        StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest,
        parent equity 6,741m). When both totals exist for the same period, the
        one satisfying assets = liabilities + equity (2%) wins; without a
        liabilities fact, a negative NCI-inclusive total never overrides a
        positive parent total.
        """
        preferred = cls._latest(gaap, ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"))
        including = cls._latest(gaap, ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",))
        parent = cls._latest(gaap, ("StockholdersEquity",))
        if not (preferred and including and parent) or including.get("end") != parent.get("end"):
            return preferred
        if preferred.get("end") != including.get("end"):
            return preferred
        inc, par = cls._value(including), cls._value(parent)
        if inc is None or par is None or inc == par:
            return preferred
        a = cls._value(assets) if assets and assets.get("end") == including.get("end") else None
        l = cls._value(liabilities) if liabilities and liabilities.get("end") == including.get("end") else None
        if a and l is not None:
            def ties(e: float) -> bool:
                return abs(a - (l + e)) <= 0.02 * abs(a)
            if not ties(inc) and ties(par):
                return parent
            return including
        if inc < 0 < par:
            return parent
        return including

    @staticmethod
    def _value(row: Optional[dict]) -> Optional[float]:
        if not row:
            return None
        value = row.get("val")
        return float(value) if isinstance(value, (int, float)) else None

    @staticmethod
    def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
        if current is None or previous in (None, 0):
            return None
        return (current / previous - 1.0) * 100.0

    @staticmethod
    def _margin(income: Optional[float], revenue: Optional[float]) -> Optional[float]:
        if income is None or revenue in (None, 0):
            return None
        return income / revenue * 100.0

    def _with_newer_filing_instance(self, cik: int, gaap: dict) -> dict:
        """Add facts of a newer filed annual 10-K that companyfacts lags behind.

        Same strict rules as the 20-F reader: the instance identifier must equal
        the identity-verified CIK, only non-dimensional fiscal-year contexts are
        used, and conflicting duplicates are dropped. Failure never raises: the
        companyfacts result (and its freshness gate) stands unchanged.
        """
        latest = ""
        for tag in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "NetIncomeLoss", "ProfitLoss", "Assets"):
            rows = self._annual_rows(gaap.get(tag) or {})
            if rows:
                latest = max(latest, str(rows[0].get("end") or ""))
        try:
            age_days = (date.today() - date.fromisoformat(latest)).days if latest else None
        except ValueError:
            age_days = None
        if age_days is not None and age_days <= COMPANYFACTS_LAG_CHECK_DAYS:
            return gaap
        reader = SECFilingInstanceReader(get_json=self._get_json, user_agent=self.user_agent, taxonomy="us-gaap")
        try:
            extra, filing = reader.newer_annual_facts(cik, latest or None)
        except GlobalProviderError:
            return gaap
        return merge_facts(gaap, extra) if filing else gaap

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.strip().upper() != "US":
            raise GlobalProviderError("SEC EDGAR fundamentals adapter only supports US issuers")

        cik = self._resolve_cik(company)
        padded = f"{cik:010d}"
        source_url = f"{SEC_FACTS_BASE}/CIK{padded}.json"
        payload = self._get_json(source_url)
        gaap = self._facts(payload)
        listed_entity_name = str(payload.get("entityName") or company.name)
        predecessor_cik = VERIFIED_PREDECESSOR_CIKS.get(cik)
        if predecessor_cik and not self._has_annual_facts(gaap):
            payload = self._get_json(f"{SEC_FACTS_BASE}/CIK{predecessor_cik:010d}.json")
            gaap = self._facts(payload)
            padded = f"{predecessor_cik:010d}"
            source_url = f"{SEC_FACTS_BASE}/CIK{padded}.json"
        else:
            predecessor_cik = None
        if not gaap:
            raise GlobalProviderError(f"SEC returned no standard US-GAAP company facts for {company.identity()}")
        gaap = self._with_newer_filing_instance(int(cik if not predecessor_cik else predecessor_cik), gaap)

        revenues = self._annual_series(gaap, ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"))
        net_income = self._annual_series(gaap, ("NetIncomeLoss", "ProfitLoss"))
        gross_profit = self._latest(gaap, ("GrossProfit",))
        operating_income = self._latest(gaap, ("OperatingIncomeLoss",))
        assets = self._latest(gaap, ("Assets",))
        liabilities = self._latest(gaap, ("Liabilities",))
        equity = self._consistent_equity(gaap, assets, liabilities)
        retained_earnings = self._latest(gaap, ("RetainedEarningsAccumulatedDeficit",))
        current_assets = self._latest(gaap, ("AssetsCurrent",))
        current_liabilities = self._latest(gaap, ("LiabilitiesCurrent",))
        cash = self._latest(gaap, ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"))
        ocf = self._latest(gaap, ("NetCashProvidedByUsedInOperatingActivities",))
        capex = self._latest(gaap, ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForAdditionsToPropertyPlantAndEquipment"))
        debt_current = self._latest(gaap, ("LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtCurrent"))
        debt_noncurrent = self._latest(gaap, ("LongTermDebtAndFinanceLeaseObligationsNoncurrent", "LongTermDebtNoncurrent"))
        debt_total = self._latest(gaap, ("LongTermDebtAndFinanceLeaseObligations", "LongTermDebt"))
        dna_candidates = {tag: self._latest(gaap, (tag,)) for tag in DNA_TAGS_COMPLETE + DNA_TAGS_PARTIAL}
        interest = self._latest(gaap, ("InterestExpenseNonOperating", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestExpense"))
        eps = self._latest(gaap, ("EarningsPerShareDiluted", "EarningsPerShareBasic"))
        dividend_per_share = self._latest(
            gaap,
            (
                "CommonStockDividendsPerShareDeclared",
                "CommonStockDividendsPerShareCashPaid",
            ),
        )
        # Only use a US-GAAP shares-count concept here. Do not substitute equity
        # or paid-in-capital dollar concepts, which would silently corrupt market cap.
        shares = self._latest(gaap, ("CommonStockSharesOutstanding",))

        # Anchor the normalized snapshot to one fiscal period. A company can
        # legitimately stop using a generic revenue concept (for example a
        # pre-revenue biotech) while its balance sheet, loss and cash flow keep
        # advancing. Never let one stale concept date the whole filing, and
        # never mix an older fact into a newer normalized statement.
        core_rows = [
            revenues[0] if revenues else None,
            net_income[0] if net_income else None,
            assets,
            liabilities,
            equity,
            current_assets,
            current_liabilities,
            cash,
            ocf,
            eps,
        ]
        period_end = max(
            (str(row.get("end") or "") for row in core_rows if row and row.get("end")),
            default="",
        ) or None
        if period_end is None:
            # Interim-only filers (new registrants, successor issuers) must not
            # attach an empty "official" source that Evidence counts as current.
            raise GlobalProviderError(
                f"SEC company facts contain no annual 10-K/20-F period for {company.identity()} (CIK {cik})"
            )

        def current_period_row(row: Optional[dict]) -> Optional[dict]:
            if row is None or period_end is None:
                return row
            return row if str(row.get("end") or "") == period_end else None

        # Some issuers use a calendar-year balance-sheet date and a 52/53-week
        # income-statement date in the SAME audited accession (BTBD FY2024:
        # 2024-12-31 vs 2024-12-29). Permit a tiny date offset only when the
        # SEC accession matches; never merge distinct filings or fiscal years.
        anchor_accessions = {
            str(row.get("accn")) for row in core_rows
            if row and row.get("end") == period_end and row.get("accn")
        }

        def same_audited_period(row: dict) -> bool:
            end = str(row.get("end") or "")
            if end == period_end:
                return True
            if not (end and period_end and row.get("accn") and str(row["accn"]) in anchor_accessions):
                return False
            try:
                return 0 < (date.fromisoformat(period_end) - date.fromisoformat(end)).days <= 3
            except ValueError:
                return False

        def current_series_row(rows: list[dict]) -> Optional[dict]:
            if period_end is None:
                return rows[0] if rows else None
            return next((row for row in rows if same_audited_period(row)), None)

        def previous_series_row(rows: list[dict], current: Optional[dict]) -> Optional[dict]:
            if current is None:
                return None
            if period_end is None:
                return rows[1] if len(rows) > 1 else None
            return next(
                (
                    row for row in rows
                    if str(row.get("end") or "")
                    and str(row.get("end") or "") < period_end
                ),
                None,
            )

        revenue_row = current_series_row(revenues)
        revenue_prev_row = previous_series_row(revenues, revenue_row)
        income_row = current_series_row(net_income)
        income_prev_row = previous_series_row(net_income, income_row)

        gross_profit = current_period_row(gross_profit)
        operating_income = current_period_row(operating_income)
        assets = current_period_row(assets)
        liabilities = current_period_row(liabilities)
        equity = current_period_row(equity)
        retained_earnings = current_period_row(retained_earnings)
        current_assets = current_period_row(current_assets)
        current_liabilities = current_period_row(current_liabilities)
        cash = current_period_row(cash)
        ocf = current_period_row(ocf)
        capex = current_period_row(capex)
        debt_current = current_period_row(debt_current)
        debt_noncurrent = current_period_row(debt_noncurrent)
        debt_total = current_period_row(debt_total)
        interest = current_period_row(interest)
        # A stale complete tag (TSLA DepreciationAndAmortization = FY2017) must
        # not shadow the current-period tag, so choose by period, not by order.
        dna_tag, dna = next(
            ((tag, row) for tag, row in dna_candidates.items() if current_period_row(row)),
            (None, None),
        )
        operating_income_value = self._value(operating_income)
        dna_value = self._value(dna)
        ebitda = None
        if operating_income_value is not None and dna_value is not None and dna_value >= 0:
            ebitda = operating_income_value + dna_value
        eps = current_period_row(eps)
        dividend_per_share = current_period_row(dividend_per_share)

        revenue = self._value(revenue_row)
        revenue_prev = self._value(revenue_prev_row)
        income = self._value(income_row)
        income_prev = self._value(income_prev_row)
        ocf_value = self._value(ocf)
        capex_value = self._value(capex)
        fcf = None if ocf_value is None or capex_value is None else ocf_value - abs(capex_value)
        total_debt = self._value(debt_total)
        if total_debt is None:
            parts = [
                value
                for value in (self._value(debt_current), self._value(debt_noncurrent))
                if value is not None
            ]
            total_debt = sum(parts) if parts else None

        # SEC companyfacts often omits the standalone Liabilities tag.
        # Derive it only from same-period assets and consolidated equity.
        liability_value = self._value(liabilities)
        if liability_value is None and assets and equity:
            asset_value = self._value(assets)
            equity_value = self._value(equity)
            if asset_value is not None and equity_value is not None and asset_value >= equity_value:
                liability_value = asset_value - equity_value

        current_rows = [
            revenue_row,
            income_row,
            gross_profit,
            operating_income,
            assets,
            liabilities,
            equity,
            current_assets,
            current_liabilities,
            cash,
            ocf,
            capex,
            debt_current,
            debt_noncurrent,
            debt_total,
            interest,
            eps,
            dividend_per_share,
        ]
        filed_at = max(
            (str(row.get("filed") or "") for row in current_rows if row and row.get("filed")),
            default="",
        ) or None

        enriched = replace(
            company,
            name=listed_entity_name,
            reporting_currency=company.reporting_currency or "USD",
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=self._pct_change(revenue, revenue_prev),
            gross_profit=self._value(gross_profit),
            operating_income=self._value(operating_income),
            net_income=income,
            net_margin_pct=self._margin(income, revenue),
            net_margin_prev_pct=self._margin(income_prev, revenue_prev),
            total_assets=self._value(assets),
            total_liabilities=liability_value,
            total_equity=self._value(equity),
            retained_earnings=self._value(retained_earnings),
            current_assets=self._value(current_assets),
            current_liabilities=self._value(current_liabilities),
            cash_and_equivalents=self._value(cash),
            operating_cash_flow=ocf_value,
            free_cash_flow=fcf,
            total_debt=total_debt,
            interest_expense=self._value(interest),
            ebitda=company.ebitda if company.ebitda is not None else ebitda,
            eps=self._value(eps),
            dividend_per_share=self._value(dividend_per_share),
            shares_outstanding=company.shares_outstanding or self._value(shares),
            filing_period_end=period_end,
            filing_observed_at=filed_at,
            raw_provider_fields={
                **company.raw_provider_fields,
                "sec_cik": cik,
                **({"ebitda_derivation": {
                    "formula": f"OperatingIncomeLoss + {dna_tag}",
                    "operating_income": operating_income_value,
                    "depreciation_amortization": dna_value,
                    "period_end": period_end,
                    "lower_bound": dna_tag in DNA_TAGS_PARTIAL,
                }} if ebitda is not None else {}),
                **({"sec_predecessor_cik": predecessor_cik} if predecessor_cik else {}),
            },
        )
        if not enriched.sector:
            sic, sic_desc = self._sic(int(cik if not predecessor_cik else predecessor_cik))
            sector = sector_from_sic(sic)
            if sector:
                enriched = replace(
                    enriched,
                    sector=sector,
                    industry=enriched.industry or sic_desc,
                    raw_provider_fields={**enriched.raw_provider_fields, "sec_sic": sic, "sector_source": "sec-sic"},
                )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_regulatory_xbrl",
                source_id=f"CIK{padded}",
                source_url=source_url,
                observed_at=filed_at,
                period_end=period_end,
                quality=1.0,
                notes=(
                    f"predecessor registrant CIK {predecessor_cik} annual filing (successor CIK {cik} has no annual facts yet); "
                    if predecessor_cik else ""
                ) + "standard US-GAAP facts from SEC companyfacts; annual 10-K/10-K-A/20-F/20-F-A or audited FY facts from 10-12B/10-12G registration statements",
            ),
        )
