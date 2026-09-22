"""Two-stage market scanning for BIAP Global.

Stage 1 is intentionally cheap: discover the selected exchange universe and use
batch quotes to rank by tradability/liquidity. Stage 2 deeply analyzes a bounded
shortlist with market history, official filings and all six BIAP Global agents.
When the live feed is unavailable, previously verified market snapshots may be
used for a clearly labelled CACHED_SCAN; EvidenceAgent still controls freshness
and can block stale data. Results are never padded or fabricated.
"""

from __future__ import annotations

from datetime import date
import math
import os
from typing import Any, Optional

import httpx

from .country_packs import ExchangeSpec, get_exchange
from .models import GlobalCompany
from .providers import GlobalProviderError
from .runtime import build_registry
from .service import analyze_company


class GlobalMarketScanner:
    def __init__(self, *, timeout: float = 20.0, batch_size: int = 100) -> None:
        self.timeout = max(5.0, float(timeout))
        self.batch_size = max(1, min(int(batch_size), 200))
        self.market_api_key = (os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "").strip()
        self.market_base = os.environ.get("BIAP_GLOBAL_MARKET_BASE", "https://api.twelvedata.com").rstrip("/")

    @staticmethod
    def _float(value: Any) -> Optional[float]:
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _date(value: Any) -> Optional[date]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

    def _batch_quote_request(self, symbols: list[str], country: str, spec: ExchangeSpec, *, use_mic: bool) -> dict:
        if not self.market_api_key:
            raise GlobalProviderError("BIAP_GLOBAL_MARKET_API_KEY is required for live non-Iran market scanning")
        params: dict[str, Any] = {
            "symbol": ",".join(symbols),
            "interval": "1day",
            "country": country.upper(),
            "apikey": self.market_api_key,
        }
        if use_mic and spec.mic:
            params["mic_code"] = spec.mic
        else:
            params["exchange"] = spec.label
        try:
            with httpx.Client(timeout=self.timeout, headers={"Accept": "application/json"}) as client:
                response = client.get(f"{self.market_base}/quote", params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"batch quote failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError("unexpected batch quote response")
        return payload

    @staticmethod
    def _flatten_batch(payload: dict) -> list[dict]:
        if payload.get("symbol"):
            return [payload]
        rows: list[dict] = []
        for value in payload.values():
            if not isinstance(value, dict):
                continue
            row = value.get("data") if isinstance(value.get("data"), dict) else value
            if row.get("symbol") and row.get("status") != "error":
                rows.append(row)
        return rows

    def _batch_quotes(self, instruments: list[GlobalCompany], country: str, spec: ExchangeSpec) -> tuple[list[dict], list[str]]:
        by_ticker = {item.ticker.upper(): item for item in instruments}
        accepted_mics = set(spec.accepted_mics)
        results: list[dict] = []
        errors: list[str] = []
        symbols = [item.ticker for item in instruments]

        for start in range(0, len(symbols), self.batch_size):
            batch = symbols[start : start + self.batch_size]
            try:
                payload = self._batch_quote_request(batch, country, spec, use_mic=True)
                rows = self._flatten_batch(payload)
                if not rows and spec.mic_aliases:
                    payload = self._batch_quote_request(batch, country, spec, use_mic=False)
                    rows = self._flatten_batch(payload)
            except GlobalProviderError as exc:
                errors.append(f"batch {start // self.batch_size + 1}: {str(exc)[:200]}")
                continue

            for row in rows:
                ticker = str(row.get("symbol") or "").strip().upper()
                if ticker not in by_ticker:
                    continue
                returned_mic = str(row.get("mic_code") or "").strip().upper() or None
                if returned_mic and accepted_mics and returned_mic not in accepted_mics:
                    continue
                price = self._float(row.get("close") or row.get("price"))
                avg_volume = self._float(row.get("average_volume"))
                volume = self._float(row.get("volume"))
                if price is None or price <= 0:
                    continue
                effective_volume = avg_volume if avg_volume and avg_volume > 0 else volume
                if effective_volume is None or effective_volume <= 0:
                    continue
                fifty_two = row.get("fifty_two_week") if isinstance(row.get("fifty_two_week"), dict) else {}
                high = self._float(fifty_two.get("high"))
                low = self._float(fifty_two.get("low"))
                range_position = None
                if high is not None and low is not None and high > low:
                    range_position = max(0.0, min(1.0, (price - low) / (high - low)))
                quote_date = self._date(row.get("datetime"))
                results.append({
                    "ticker": ticker,
                    "price": price,
                    "averageVolume": effective_volume,
                    "liquidityValue": price * effective_volume,
                    "rangePosition": range_position,
                    "quoteDate": quote_date.isoformat() if quote_date else None,
                    "mic": returned_mic,
                })
        return results, errors

    @staticmethod
    def _cached_quotes(companies: list[GlobalCompany], allowed_tickers: set[str]) -> list[dict]:
        results: list[dict] = []
        for company in companies:
            ticker = company.ticker.upper()
            if ticker not in allowed_tickers:
                continue
            price = company.price
            effective_volume = company.avg_volume_30d or company.volume_today
            if price is None or price <= 0 or effective_volume is None or effective_volume <= 0:
                continue
            range_position = None
            if company.price_52w_high is not None and company.price_52w_low is not None and company.price_52w_high > company.price_52w_low:
                range_position = max(0.0, min(1.0, (price - company.price_52w_low) / (company.price_52w_high - company.price_52w_low)))
            results.append({
                "ticker": ticker,
                "price": price,
                "averageVolume": effective_volume,
                "liquidityValue": price * effective_volume,
                "rangePosition": range_position,
                "quoteDate": company.price_observed_at[:10] if company.price_observed_at else None,
                "mic": company.mic_code,
                "cache": company.raw_provider_fields.get("market_cache"),
            })
        return results

    @staticmethod
    def _screen_rank(row: dict) -> tuple[float, float]:
        liquidity = max(1.0, float(row.get("liquidityValue") or 0.0))
        liquidity_score = math.log10(liquidity)
        position = row.get("rangePosition")
        range_neutrality = 0.0 if position is None else 1.0 - abs(float(position) - 0.5)
        return liquidity_score, range_neutrality

    @staticmethod
    def _deep_results(
        shortlist_tickers: list[str],
        selected_universe: list[GlobalCompany],
        quote_by_ticker: dict[str, dict],
        registry,
    ) -> list[dict]:
        instrument_by_ticker = {item.ticker.upper(): item for item in selected_universe}
        deep_results: list[dict] = []
        for ticker in shortlist_tickers:
            company = instrument_by_ticker.get(ticker)
            if company is None:
                continue
            try:
                result = analyze_company(company, registry=registry)
            except Exception as exc:
                deep_results.append({
                    "ticker": ticker,
                    "call": "NO_RECOMMENDATION",
                    "score": 0.0,
                    "confidence": 0.0,
                    "error": str(exc)[:300],
                })
                continue
            result["screening"] = quote_by_ticker.get(ticker)
            deep_results.append(result)
        return deep_results

    @staticmethod
    def _recommendations(deep_results: list[dict], top_n: int) -> list[dict]:
        buys = [result for result in deep_results if result.get("call") == "BUY_CANDIDATE"]
        buys.sort(
            key=lambda result: float(result.get("score") or 0.0) * float(result.get("confidence") or 0.0),
            reverse=True,
        )
        unique: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for result in buys:
            company = result.get("company") if isinstance(result.get("company"), dict) else {}
            key = (
                str(result.get("country") or company.get("country") or "").strip().upper(),
                str(result.get("exchange") or company.get("exchange") or "").strip().upper(),
                str(result.get("ticker") or company.get("ticker") or "").strip().upper(),
            )
            if key[2] and key in seen:
                continue
            if key[2]:
                seen.add(key)
            unique.append(result)
            if len(unique) >= top_n:
                break
        return unique

    def scan(
        self,
        *,
        country: str,
        exchange: str,
        top_n: int = 10,
        discovery_limit: int = 5000,
        deep_limit: int = 25,
    ) -> dict:
        top_n = max(1, min(int(top_n), 50))
        discovery_limit = max(top_n, min(int(discovery_limit), 5000))
        deep_limit = max(top_n, min(int(deep_limit), 100))
        spec = get_exchange(country, exchange)

        if country.upper() == "IR":
            return self._scan_iran(exchange=spec.code, top_n=top_n, deep_limit=deep_limit)

        registry = build_registry()
        universe_provider = registry.universe(country, spec.code)
        universe = list(universe_provider.list_instruments(country=country.upper(), exchange=spec.code))
        discovered_count = len(universe)
        selected_universe = universe[:discovery_limit]
        partial = discovered_count > discovery_limit

        if not self.market_api_key:
            market_provider = registry.market(country, spec.code)
            cached_companies = market_provider.cached_companies(country=country.upper(), exchange=spec.code) if hasattr(market_provider, "cached_companies") else []
            allowed_tickers = {item.ticker.upper() for item in selected_universe}
            cached_quotes = self._cached_quotes(cached_companies, allowed_tickers)
            if not cached_quotes:
                return {
                    "status": "MARKET_DATA_REQUIRED",
                    "country": country.upper(),
                    "exchange": spec.code,
                    "mic": spec.mic,
                    "requestedRecommendations": top_n,
                    "recommendationCount": 0,
                    "universeDiscovered": discovered_count,
                    "universeScreened": 0,
                    "quotesUsable": 0,
                    "deepAnalyzed": 0,
                    "screeningCoveragePct": 0.0,
                    "screeningErrors": ["Reference catalog is available; no verified price/history snapshot exists yet."],
                    "recommendations": [],
                    "deepResults": [],
                    "catalogOnly": True,
                    "cachedMarketData": False,
                    "notes": "Configure a market-data credential once to seed verified snapshots. BIAP will not produce BUY candidates from catalog metadata alone.",
                }

            ranked = sorted(cached_quotes, key=self._screen_rank, reverse=True)
            shortlist_tickers = [row["ticker"] for row in ranked[:deep_limit]]
            quote_by_ticker = {row["ticker"]: row for row in cached_quotes}
            deep_results = self._deep_results(shortlist_tickers, selected_universe, quote_by_ticker, registry)
            recommendations = self._recommendations(deep_results, top_n)
            return {
                "status": "CACHED_SCAN" if recommendations else "CACHED_NO_RECOMMENDATION",
                "country": country.upper(),
                "exchange": spec.code,
                "mic": spec.mic,
                "requestedRecommendations": top_n,
                "recommendationCount": len(recommendations),
                "universeDiscovered": discovered_count,
                "universeScreened": len(cached_quotes),
                "quotesUsable": len(cached_quotes),
                "deepAnalyzed": len(deep_results),
                "screeningCoveragePct": round(100.0 * len(cached_quotes) / discovered_count, 2) if discovered_count else 0.0,
                "screeningErrors": ["Live price/history feed unavailable; scan used persisted verified market snapshots."],
                "recommendations": recommendations,
                "deepResults": deep_results,
                "catalogOnly": False,
                "cachedMarketData": True,
                "notes": "Cached scan only. EvidenceAgent preserves original price timestamps and blocks stale or incomplete evidence.",
            }

        quotes, screening_errors = self._batch_quotes(selected_universe, country.upper(), spec)
        quote_by_ticker = {row["ticker"]: row for row in quotes}
        ranked = sorted(quotes, key=self._screen_rank, reverse=True)
        shortlist_tickers = [row["ticker"] for row in ranked[:deep_limit]]
        deep_results = self._deep_results(shortlist_tickers, selected_universe, quote_by_ticker, registry)
        recommendations = self._recommendations(deep_results, top_n)
        status = "PARTIAL_SCAN" if partial or screening_errors else "COMPLETE_SCAN"
        if not recommendations:
            status = "NO_RECOMMENDATION" if status == "COMPLETE_SCAN" else status

        return {
            "status": status,
            "country": country.upper(),
            "exchange": spec.code,
            "mic": spec.mic,
            "requestedRecommendations": top_n,
            "recommendationCount": len(recommendations),
            "universeDiscovered": discovered_count,
            "universeScreened": len(selected_universe),
            "quotesUsable": len(quotes),
            "deepAnalyzed": len(deep_results),
            "screeningCoveragePct": round(100.0 * len(selected_universe) / discovered_count, 2) if discovered_count else 0.0,
            "screeningErrors": screening_errors,
            "recommendations": recommendations,
            "deepResults": deep_results,
            "cachedMarketData": False,
            "notes": "Stage 1 ranks tradability only; BUY_CANDIDATE requires deep evidence/agent gates. Results are not padded to top_n.",
        }

    def _scan_iran(self, *, exchange: str, top_n: int, deep_limit: int) -> dict:
        from market_scanner import scan_market

        legacy = scan_market(market=exchange, max_symbols=max(50, deep_limit * 8))
        candidates = legacy.get("recommendations") if isinstance(legacy, dict) else []
        if not isinstance(candidates, list):
            candidates = []
        registry = build_registry()
        deep_results: list[dict] = []
        for row in candidates[:deep_limit]:
            ticker = str(row.get("symbol") or row.get("code") or "").strip()
            if not ticker:
                continue
            company = GlobalCompany(
                country="IR", exchange=exchange, currency="IRR", ticker=ticker,
                name=str(row.get("name") or ticker),
            )
            deep_results.append(analyze_company(company, registry=registry))
        buys = self._recommendations(deep_results, top_n)
        return {
            "status": "IR_LEGACY_SHORTLIST",
            "country": "IR",
            "exchange": exchange,
            "requestedRecommendations": top_n,
            "recommendationCount": len(buys),
            "recommendations": buys,
            "deepResults": deep_results,
            "legacyScanner": {
                "scanned": legacy.get("scanned") if isinstance(legacy, dict) else None,
                "totalUniverse": legacy.get("totalUniverse") if isinstance(legacy, dict) else None,
                "dataSource": legacy.get("dataSource") if isinstance(legacy, dict) else None,
            },
            "notes": "Iran Global scan reuses the existing Iran scanner for shortlist generation, then applies Global evidence/agent gates.",
        }
