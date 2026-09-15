"""Read-only bridge from the existing Iran BIAP pipeline into BIAP Global.

This module deliberately reuses the production-proven TSETMC/CODAL builder
without modifying it. Global Iran analysis therefore gets the same verified
legacy evidence while `main` remains untouched.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import time
from typing import Optional

from company_builder import build_company_from_quote, build_company_from_symbol
from market_data import MarketDataUnavailable, find_quote

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, MarketDataProvider, append_source


class IranLegacyProvider(MarketDataProvider, FundamentalsProvider):
    provider_id = "iran-legacy-tsetmc-codal"

    def __init__(self, *, cache_ttl: float = 30.0) -> None:
        self.cache_ttl = max(1.0, float(cache_ttl))
        self._cache: dict[str, tuple[float, dict]] = {}

    def _legacy(self, company: GlobalCompany) -> dict:
        key = company.ticker.strip()
        cached = self._cache.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < self.cache_ttl:
            return cached[1]
        try:
            quote = find_quote(key)
        except MarketDataUnavailable:
            quote = None
        if quote is not None:
            record = build_company_from_quote(quote, codal_symbol=quote.name)
        else:
            record = build_company_from_symbol(key)
        if not isinstance(record, dict):
            raise GlobalProviderError(f"Iran legacy pipeline returned no verified data for {key}")
        self._cache[key] = (now, record)
        return record

    @staticmethod
    def _float(value) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def enrich_market(self, company: GlobalCompany) -> GlobalCompany:
        record = self._legacy(company)
        market = record.get("market") if isinstance(record.get("market"), dict) else {}
        fetched = market.get("quote_fetched_at")
        observed_at = None
        if isinstance(fetched, (int, float)):
            observed_at = datetime.fromtimestamp(float(fetched), tz=timezone.utc).isoformat()

        performance = market.get("tindex_performance") if isinstance(market.get("tindex_performance"), dict) else {}
        enriched = replace(
            company,
            name=str(record.get("name_fa") or company.name),
            price=self._float(market.get("price")),
            price_observed_at=observed_at,
            volume_today=self._float(market.get("volume_today")),
            avg_volume_30d=self._float(market.get("avg_volume_30d")),
            market_cap=self._float(market.get("market_cap")),
            shares_outstanding=self._float(market.get("shares_outstanding")),
            price_52w_high=self._float(market.get("price_52w_high")),
            price_52w_low=self._float(market.get("price_52w_low")),
            pe=self._float(market.get("pe")),
            sector_pe=self._float(market.get("sector_avg_pe")),
            eps=self._float(market.get("eps_value") or market.get("estimated_eps")),
            sector=str(market.get("sector_name") or company.sector or "") or None,
            return_1m_pct=self._float(performance.get("return_1m")),
            return_3m_pct=self._float(performance.get("return_3m")),
            return_6m_pct=self._float(performance.get("return_6m")),
            volatility_annualized_pct=self._float(performance.get("volatility")),
            max_drawdown_pct=self._float(performance.get("max_drawdown")),
            raw_provider_fields={**company.raw_provider_fields, "iran_legacy_availability": record.get("data_available")},
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_market_data",
                source_id=company.ticker,
                observed_at=observed_at,
                quality=1.0,
                notes="read-only bridge to existing TSETMC market path",
            ),
        )

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        record = self._legacy(company)
        codal = record.get("codal") if isinstance(record.get("codal"), dict) else {}
        if not codal:
            return company

        revenue = self._float(codal.get("revenue_current"))
        revenue_prev = self._float(codal.get("revenue_prev"))
        net_income = self._float(codal.get("net_profit_current"))
        enriched = replace(
            company,
            reporting_currency="IRR",
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=self._float(codal.get("revenue_yoy_pct")),
            gross_profit=self._float(codal.get("gross_profit_current")),
            net_income=net_income,
            net_margin_pct=self._float(codal.get("net_margin_pct")),
            net_margin_prev_pct=self._float(codal.get("net_margin_prev_pct")),
            total_assets=self._float(codal.get("total_assets_current")),
            total_liabilities=self._float(codal.get("total_liabilities_current")),
            total_equity=self._float(codal.get("total_equity_current")),
            audit_opinion=codal.get("audit_opinion"),
            report_scope=codal.get("report_scope"),
            raw_provider_fields={
                **company.raw_provider_fields,
                "iran_codal_tracing_no": codal.get("tracing_no"),
                "iran_codal_report_title": codal.get("report_title"),
            },
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_regulatory_filing",
                source_id=str(codal.get("tracing_no") or company.ticker),
                source_url=codal.get("report_url"),
                quality=1.0,
                notes="read-only bridge to existing CODAL verified fundamentals",
            ),
        )
