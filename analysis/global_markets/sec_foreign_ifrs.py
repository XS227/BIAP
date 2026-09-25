"""SEC annual IFRS fallback for non-US issuers listed in BIAP Global.

Some European issuers (for example SAP) file audited IFRS financial statements
with the U.S. SEC as foreign private issuers even when their local ESEF package
is not mirrored by filings.xbrl.org. This adapter is deliberately conservative:

* ticker lookup must resolve in the SEC public mapping;
* SEC entity legal-name core must exactly match the selected company;
* only standard ifrs-full facts from annual 20-F/20-F-A or 40-F/40-F-A filings are used;
* missing concepts remain None and no vendor metric is promoted to official.

Raw SEC companyfacts responses are inherited from the existing persistent SEC
cache, so the same historical source JSON is retained on the BIAP server.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from .cached_sec_edgar import CachedSECEdgarFundamentalsProvider
from .gleif import _legal_core
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, append_source
from .sec_edgar import SEC_FACTS_BASE


# Local exchange symbols can differ from the issuer's US ADR ticker. Aliases are
# explicit and venue-scoped; SEC legal-name equality still has to pass before
# any CompanyFacts data is accepted.
_VERIFIED_LOCAL_TICKER_ALIASES = {
    ("CH", "SIX", "NOVN"): "NVS",  # Novartis AG
}


class SECForeignIFRSFundamentalsProvider(CachedSECEdgarFundamentalsProvider):
    provider_id = "sec-edgar-foreign-ifrs-cached"

    @staticmethod
    def _facts(payload: dict) -> dict:
        facts = payload.get("facts")
        if not isinstance(facts, dict):
            return {}
        ifrs = facts.get("ifrs-full")
        return ifrs if isinstance(ifrs, dict) else {}

    @staticmethod
    def _annual_rows(concept: dict) -> list[dict]:
        units = concept.get("units") if isinstance(concept, dict) else None
        if not isinstance(units, dict):
            return []
        rows: list[dict] = []
        for unit, entries in units.items():
            if not isinstance(entries, list):
                continue
            for raw in entries:
                if not isinstance(raw, dict) or raw.get("form") not in {"20-F", "20-F/A", "40-F", "40-F/A"}:
                    continue
                if raw.get("fp") not in {None, "FY"} or not isinstance(raw.get("val"), (int, float)):
                    continue
                row = dict(raw)
                row["_unit"] = str(unit or "")
                rows.append(row)
        rows.sort(key=lambda row: (str(row.get("end") or ""), str(row.get("filed") or "")), reverse=True)
        return rows

    @staticmethod
    def _currency(row: Optional[dict]) -> Optional[str]:
        if not row:
            return None
        unit = str(row.get("_unit") or "").strip().upper()
        if len(unit) == 3 and unit.isalpha():
            return unit
        return None

    @staticmethod
    def _identity_matches(company: GlobalCompany, entity_name: str) -> bool:
        company_core = _legal_core(company.name)
        entity_core = _legal_core(entity_name)
        return bool(company_core and entity_core and company_core == entity_core)

    def _resolve_cik(self, company: GlobalCompany) -> int:
        explicit_alias = str(company.raw_provider_fields.get("sec_ticker_alias") or "").strip().upper()
        key = (
            company.country.strip().upper(),
            company.exchange.strip().upper(),
            company.ticker.strip().upper(),
        )
        alias = explicit_alias or _VERIFIED_LOCAL_TICKER_ALIASES.get(key, "")
        if alias:
            cik = self._ticker_map().get(alias)
            if cik is None:
                raise GlobalProviderError(f"SEC CIK not found for verified alias {alias}")
            return cik
        return super()._resolve_cik(company)

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.strip().upper() == "US":
            raise GlobalProviderError("foreign SEC IFRS fallback is not used for US issuers")

        cik = self._resolve_cik(company)
        padded = f"{cik:010d}"
        source_url = f"{SEC_FACTS_BASE}/CIK{padded}.json"
        payload = self._get_json(source_url)
        entity_name = str(payload.get("entityName") or "").strip()
        if not entity_name or not self._identity_matches(company, entity_name):
            raise GlobalProviderError(
                f"SEC ticker identity does not match selected issuer {company.name!r}"
            )

        ifrs = self._facts(payload)
        if not ifrs:
            raise GlobalProviderError(f"SEC returned no standard IFRS company facts for {company.identity()}")

        revenues = self._annual_series(ifrs, ("Revenue", "RevenueFromContractsWithCustomers"))
        net_income = self._annual_series(ifrs, ("ProfitLoss", "ProfitLossAttributableToOwnersOfParent"))
        gross_profit = self._latest(ifrs, ("GrossProfit",))
        operating_income = self._latest(ifrs, ("OperatingProfitLoss", "ProfitLossFromOperatingActivities"))
        assets = self._latest(ifrs, ("Assets",))
        liabilities = self._latest(ifrs, ("Liabilities",))
        equity = self._latest(ifrs, ("Equity", "EquityAttributableToOwnersOfParent"))
        current_assets = self._latest(ifrs, ("CurrentAssets",))
        current_liabilities = self._latest(ifrs, ("CurrentLiabilities",))
        cash = self._latest(ifrs, ("CashAndCashEquivalents",))
        ocf = self._latest(ifrs, ("CashFlowsFromUsedInOperatingActivities",))
        capex = self._latest(ifrs, ("PurchaseOfPropertyPlantAndEquipment",))
        debt_total = self._latest(ifrs, ("Borrowings",))
        debt_current = self._latest(ifrs, ("CurrentBorrowings",))
        debt_noncurrent = self._latest(ifrs, ("NoncurrentBorrowings",))
        interest = self._latest(ifrs, ("FinanceCosts", "InterestExpense"))
        eps = self._latest(ifrs, ("DilutedEarningsLossPerShare", "BasicEarningsLossPerShare"))

        revenue = self._value(revenues[0] if revenues else None)
        revenue_prev = self._value(revenues[1] if len(revenues) > 1 else None)
        income = self._value(net_income[0] if net_income else None)
        income_prev = self._value(net_income[1] if len(net_income) > 1 else None)
        ocf_value = self._value(ocf)
        capex_value = self._value(capex)
        free_cash_flow = None if ocf_value is None or capex_value is None else ocf_value - abs(capex_value)

        total_debt = self._value(debt_total)
        if total_debt is None:
            parts = [value for value in (self._value(debt_current), self._value(debt_noncurrent)) if value is not None]
            total_debt = sum(parts) if parts else None

        period_row = revenues[0] if revenues else (net_income[0] if net_income else assets)
        period_end = (str(period_row.get("end") or "") or None) if period_row else None
        filed_at = (str(period_row.get("filed") or "") or None) if period_row else None
        reporting_currency = self._currency(period_row) or company.reporting_currency
        filing_form = str((period_row or {}).get("form") or "").strip() or None

        enriched = replace(
            company,
            name=entity_name or company.name,
            reporting_currency=reporting_currency,
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=self._pct_change(revenue, revenue_prev),
            gross_profit=self._value(gross_profit),
            operating_income=self._value(operating_income),
            net_income=income,
            net_margin_pct=self._margin(income, revenue),
            net_margin_prev_pct=self._margin(income_prev, revenue_prev),
            total_assets=self._value(assets),
            total_liabilities=self._value(liabilities),
            total_equity=self._value(equity),
            current_assets=self._value(current_assets),
            current_liabilities=self._value(current_liabilities),
            cash_and_equivalents=self._value(cash),
            operating_cash_flow=ocf_value,
            free_cash_flow=free_cash_flow,
            total_debt=total_debt,
            interest_expense=self._value(interest),
            eps=self._value(eps),
            filing_period_end=period_end,
            filing_observed_at=filed_at,
            raw_provider_fields={**company.raw_provider_fields, "sec_cik": cik, "sec_form": filing_form},
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
                notes="standard IFRS facts from SEC companyfacts; annual 20-F/40-F and amendments only; issuer legal-name core verified",
            ),
        )
