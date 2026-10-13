"""Two-stage market scanning for BIAP Global.

Stage 1 is intentionally cheap: discover the selected exchange universe and use
batch quotes to rank by tradability/liquidity. Stage 2 deeply analyzes a bounded
shortlist with market history, official filings and all six BIAP Global agents.
When the live feed is unavailable, previously verified market snapshots may be
used for a clearly labelled CACHED_SCAN; EvidenceAgent still controls freshness
and can block stale data. Results are never padded or fabricated.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import math
import os
from typing import Any, Optional

import httpx

from .analysis_ledger import AnalysisLedger, drain, rss_mb
from .b3_official import B3OfficialClient
from .bme_official import BMEOfficialDailyClient
from .bist_official import BISTOfficialDailyClient
from .issuer import collapse_issuers
from .country_packs import ExchangeSpec, get_country_pack, get_exchange
from .eodhd_bulk import EODHDBulkEODProvider
from .euronext_live import EuronextLiveRegulatedClient
from .lse_official import LSEOfficialClient
from .models import GlobalCompany, SourceEvidence
from .nasdaq_nordic import NasdaqNordicOfficialClient
from .providers import GlobalProviderError
from .runtime import build_registry
from .service import analyze_company
from .us_official import NasdaqUSFullScreenerClient
from .xetra_delayed import DeutscheBoerseXetraDelayedClient


class GlobalMarketScanner:
    def __init__(self, *, timeout: float = 20.0, batch_size: int = 100) -> None:
        self.timeout = max(5.0, float(timeout))
        self.batch_size = max(1, min(int(batch_size), 200))
        self.market_api_key = (os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "").strip()
        self.eodhd_api_token = (os.environ.get("BIAP_EODHD_API_TOKEN") or "").strip()
        self.eodhd_bulk = EODHDBulkEODProvider(self.eodhd_api_token, timeout=max(20.0, self.timeout)) if self.eodhd_api_token else None
        self.euronext_live = EuronextLiveRegulatedClient(timeout=max(20.0, self.timeout))
        self.lse_official = LSEOfficialClient(timeout=max(30.0, self.timeout))
        self.nasdaq_nordic = NasdaqNordicOfficialClient(timeout=max(20.0, self.timeout))
        self.b3_official = B3OfficialClient(timeout=max(45.0, self.timeout))
        self.bme_official = BMEOfficialDailyClient(timeout=max(30.0, self.timeout))
        self.bist_official = BISTOfficialDailyClient(timeout=max(30.0, self.timeout))
        self.us_screener = NasdaqUSFullScreenerClient(timeout=max(45.0, self.timeout))
        self.xetra_delayed = DeutscheBoerseXetraDelayedClient(timeout=max(90.0, self.timeout))
        self.market_base = os.environ.get("BIAP_GLOBAL_MARKET_BASE", "https://api.twelvedata.com").rstrip("/")
        self.min_market_coverage_pct = max(0.0, min(100.0, float(os.environ.get("BIAP_GLOBAL_MIN_MARKET_COVERAGE_PCT", "90"))))
        self.min_fundamental_coverage_pct = max(0.0, min(100.0, float(os.environ.get("BIAP_GLOBAL_MIN_FUNDAMENTAL_COVERAGE_PCT", "70"))))

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
        if not self.market_api_key and self.eodhd_bulk is None:
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
    def _seed_screening_quote(company: GlobalCompany, quote: Optional[dict]) -> GlobalCompany:
        """Carry a verified stage-one quote into stage-two enrichment.

        Whole-market scanners already verified the listing/price against their
        exchange-wide source. Stage two may still enrich with history, but a
        vendor-history outage must not erase the official current price that
        selected the candidate in stage one.
        """
        if not isinstance(quote, dict):
            return company
        try:
            price = float(quote.get("price"))
        except (TypeError, ValueError):
            return company
        provider = str(quote.get("provider") or "").strip()
        if price <= 0 or not provider or quote.get("cache"):
            return company

        quote_date = str(quote.get("quoteDate") or "").strip()
        observed_at = None
        if quote_date:
            observed_at = (
                quote_date
                if "T" in quote_date
                else f"{quote_date[:10]}T00:00:00+00:00"
            )
        try:
            volume = float(quote.get("averageVolume") or 0.0)
        except (TypeError, ValueError):
            volume = 0.0

        official = provider.lower().startswith("official-")
        source = SourceEvidence(
            provider=provider,
            source_type="official_exchange_market_quote" if official else "verified_market_price_quote",
            source_id=f"{company.country}:{company.exchange}:{company.ticker}:{quote_date or 'latest'}",
            source_url=str(quote.get("sourceUrl") or "").strip() or None,
            observed_at=observed_at,
            quality=1.0 if official else 0.90,
            notes="Stage-one full-market screening quote carried into deep analysis.",
        )
        return replace(
            company,
            price=price,
            price_observed_at=observed_at or company.price_observed_at,
            volume_today=max(0.0, volume) if volume else company.volume_today,
            raw_provider_fields={
                **company.raw_provider_fields,
                "stage_one_market_provider": provider,
                "stage_one_quote_date": quote_date or None,
                "stage_one_liquidity_value": quote.get("liquidityValue"),
            },
            sources=[*company.sources, source],
        )

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
            quote = quote_by_ticker.get(ticker)
            company = GlobalMarketScanner._seed_screening_quote(company, quote)
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
            result["screening"] = quote
            deep_results.append(result)
        return deep_results

    @staticmethod
    def _verified_fundamental_count(deep_results: list[dict]) -> int:
        verified = 0
        for result in deep_results:
            evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
            missing = evidence.get("missing_critical") or evidence.get("missingCritical") or []
            if not isinstance(missing, (list, tuple)):
                missing = []
            reasoning = str(evidence.get("reasoning") or "")
            if "fundamental_source" not in missing and "missing=fundamental_source" not in reasoning:
                company = result.get("company") if isinstance(result.get("company"), dict) else {}
                if company:
                    verified += 1
        return verified

    def _readiness(
        self,
        *,
        country: str,
        exchange: str,
        universe_count: int,
        screened_count: int,
        deep_results: list[dict],
        live_market_data: bool,
        market_source: str,
        partial_universe: bool,
        screening_errors: list[str],
        universe_authoritative: bool,
        universe_source: str,
        analysis: Optional[dict] = None,
    ) -> dict:
        pack = get_country_pack(country)
        market_coverage = 0.0 if universe_count <= 0 else 100.0 * screened_count / universe_count
        if analysis is not None:
            analyzed = int(analysis.get("deepAnalyzed") or 0)
            verified_fundamentals = max(0, analyzed - int(analysis.get("fundamentalSourceMissing") or 0))
        else:
            analyzed = len(deep_results)
            verified_fundamentals = self._verified_fundamental_count(deep_results)
        fundamental_coverage = 0.0 if not analyzed else 100.0 * verified_fundamentals / analyzed
        reasons: list[str] = []
        if not universe_authoritative:
            reasons.append("authoritative_universe_unavailable")
        if not live_market_data:
            reasons.append("full_market_source_unavailable")
        if partial_universe:
            reasons.append("universe_discovery_truncated")
        if market_coverage < self.min_market_coverage_pct:
            reasons.append("market_coverage_below_threshold")
        if analyzed and fundamental_coverage < self.min_fundamental_coverage_pct:
            reasons.append("official_fundamental_coverage_below_threshold")
        if screening_errors:
            reasons.append("market_data_batch_errors")
        ranking_eligible = not reasons and universe_count > 0 and analyzed > 0
        return {
            "status": "READY" if ranking_eligible else "BLOCKED" if not live_market_data else "PARTIAL",
            "rankingEligible": ranking_eligible,
            "universeSource": universe_source,
            "universeAuthoritative": universe_authoritative,
            "marketSource": market_source if live_market_data else "stored market records only",
            "fundamentalsSource": pack.official_evidence_source,
            "eligibleEquities": universe_count,
            "screenedEquities": screened_count,
            "marketCoveragePct": round(market_coverage, 2),
            "deepAnalyzed": analyzed,
            "analysisQueued": int((analysis or {}).get("queued") or 0),
            "verifiedFundamentals": verified_fundamentals,
            "fundamentalCoveragePct": round(fundamental_coverage, 2),
            "requiredMarketCoveragePct": self.min_market_coverage_pct,
            "requiredFundamentalCoveragePct": self.min_fundamental_coverage_pct,
            "reasons": reasons,
        }

    RANKING_BASIS = {
        "criterion": "score_x_confidence",
        "formula": "score * confidence (Kiasha score after evidence multiplier, times overall calibrated confidence)",
        "scope": "BUY_CANDIDATE with evidence PASS, one security per issuer",
        "note": "Market, Kiasha and Portfolio must all use this order; rawScoreRank is shown only for comparison.",
    }

    @classmethod
    def annotate_ranking(cls, recommendations: list[dict], all_buys: list[dict]) -> list[dict]:
        """Attach explicit rank/criterion to each pick (copies; stored results untouched)."""
        by_raw = sorted(
            all_buys,
            key=lambda r: float(r.get("score") or 0.0),
            reverse=True,
        )
        raw_rank = {str(r.get("ticker") or "").upper(): i + 1 for i, r in enumerate(by_raw)}
        out: list[dict] = []
        for index, row in enumerate(recommendations, start=1):
            score = float(row.get("score") or 0.0)
            confidence = float(row.get("confidence") or 0.0)
            out.append({
                **row,
                "rank": index,
                "rankScore": round(score * confidence, 6),
                "rankCriterion": cls.RANKING_BASIS["criterion"],
                "rawScoreRank": raw_rank.get(str(row.get("ticker") or "").upper()),
            })
        return out

    # The engine emits four calls; Watchlist and Hold are one engine state (HOLD_OR_WATCH) and are not split artificially.
    CALL_CATEGORY = {
        "BUY_CANDIDATE": "QUALIFIED_BUY",
        "HOLD_OR_WATCH": "WATCHLIST_HOLD",
        "AVOID_OR_REVIEW": "AVOID_REVIEW",
        "NO_RECOMMENDATION": "NO_SIGNAL",
    }

    @classmethod
    def ranking_groups(cls, gates: dict) -> dict:
        """Where every analyzed company sits: evidence-supported groups vs Insufficient Evidence."""
        calls = gates.get("callsAmongScored") or {}
        groups = {cat: 0 for cat in dict.fromkeys(cls.CALL_CATEGORY.values())}
        for call, n in calls.items():
            groups[cls.CALL_CATEGORY.get(call, "NO_SIGNAL")] += n
        groups["INSUFFICIENT_EVIDENCE"] = gates["analyzed"] - gates["scoredAndComplete"]
        groups["NOT_YET_ANALYZED"] = gates["universe"] - gates["analyzed"]
        return groups

    @classmethod
    def market_top10(cls, pool: list[dict], top_n: int) -> list[dict]:
        """Top evidence-supported companies of any call, one row per issuer, ranked by score*confidence.

        Unlike ``recommendations`` this is NOT a buy list: every row carries its
        actual ``call`` and ``qualifiedBuy`` says whether it also cleared the BUY gate.
        """
        rank = lambda r: float(r.get("score") or 0.0) * float(r.get("confidence") or 0.0)
        pool = sorted(pool, key=rank, reverse=True)
        pool = sorted(collapse_issuers(pool, rank), key=rank, reverse=True)[: max(1, int(top_n))]
        return [
            {
                **row,
                "rank": index,
                "rankScore": round(rank(row), 6),
                "rankCriterion": cls.RANKING_BASIS["criterion"],
                "qualifiedBuy": row.get("call") == "BUY_CANDIDATE",
                "category": cls.CALL_CATEGORY.get(str(row.get("call")), "NO_SIGNAL"),
            }
            for index, row in enumerate(pool, start=1)
        ]

    @staticmethod
    def ranking_gates(gates: dict, *, buy_after_issuer: int, ranking_eligible: bool, readiness_reasons: list[str]) -> list[dict]:
        """Ordered gate funnel: how many companies entered, passed and were rejected, and why."""
        universe, analyzed = gates["universe"], gates["analyzed"]
        passed, scored, buy = gates["evidencePass"], gates["scoredAndComplete"], gates["buyCandidates"]
        calls = gates.get("callsAmongScored") or {}
        return [
            {"gate": "market_ranking_released", "entered": universe, "passed": universe if ranking_eligible else 0,
             "rejected": 0 if ranking_eligible else universe,
             "reasons": {} if ranking_eligible else {r: universe for r in readiness_reasons or ["ranking_not_released"]}},
            {"gate": "deep_analysis_complete", "entered": universe, "passed": analyzed, "rejected": universe - analyzed,
             "reasons": {"not_yet_analyzed": universe - analyzed} if universe > analyzed else {}},
            {"gate": "evidence_pass", "entered": analyzed, "passed": passed, "rejected": analyzed - passed,
             "reasons": gates.get("evidenceNotPassReasons") or {}, "byEvidenceStatus": gates.get("evidenceNotPass") or {}},
            {"gate": "score_and_confidence_available", "entered": passed, "passed": scored, "rejected": passed - scored,
             "reasons": {"no_numeric_score_or_confidence_or_incomplete_analysis": passed - scored} if passed > scored else {}},
            {"gate": "buy_threshold", "entered": scored, "passed": buy, "rejected": scored - buy,
             "reasons": {f"call={k}": v for k, v in calls.items() if k != "BUY_CANDIDATE"}},
            {"gate": "one_security_per_issuer", "entered": buy, "passed": buy_after_issuer, "rejected": buy - buy_after_issuer,
             "reasons": {"duplicate_share_class_of_same_issuer": buy - buy_after_issuer} if buy > buy_after_issuer else {}},
        ]

    @staticmethod
    def evidence_summary(counts: dict) -> dict:
        """Evidence gate totals over EVERY deep-analyzed company (ledger), not the capped payload rows."""
        analyzed = int(counts.get("deepAnalyzed") or 0)
        return {
            "basis": "ledger_all_deep_analyzed",
            "denominator": analyzed,
            "pass": int(counts.get("evidencePass") or 0),
            "warn": int(counts.get("evidenceWarn") or 0),
            "block": int(counts.get("evidenceBlock") or 0),
            "note": "Evidence gates measure data quality only; they are not financial completeness or a recommendation. "
                    "deepResults rows are a ranked sample capped by BIAP_GLOBAL_PAYLOAD_DEEP_ROWS and must not be counted.",
        }

    @staticmethod
    def _recommendations(deep_results: list[dict], top_n: int) -> list[dict]:
        buys = [
            result for result in deep_results
            if result.get("call") == "BUY_CANDIDATE"
            and isinstance(result.get("evidence"), dict)
            and result["evidence"].get("status") == "PASS"
        ]
        buys.sort(
            key=lambda result: float(result.get("score") or 0.0) * float(result.get("confidence") or 0.0),
            reverse=True,
        )
        buys = collapse_issuers(
            buys, lambda r: float(r.get("score") or 0.0) * float(r.get("confidence") or 0.0)
        )
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

    def _stage_one_quotes(
        self, selected_universe: list[GlobalCompany], country: str, spec: ExchangeSpec, ledger: Optional[AnalysisLedger] = None,
    ) -> tuple[list[dict], list[str], str, bool]:
        """Whole-exchange screening quotes; a fresh ledger copy avoids refetching.

        A phone-triggered scan therefore only advances the analysis queue and
        never re-downloads the full market inside the HTTP request.
        """
        reuse_minutes = float(os.environ.get("BIAP_GLOBAL_STAGE1_REUSE_MINUTES", "180"))
        if ledger is not None:
            age = ledger.stage1_age_minutes()
            stored = ledger.get_meta("stage1")
            if age is not None and age < reuse_minutes and isinstance(stored, dict):
                reused = list(ledger.quotes().values())
                if reused:
                    return reused, list(stored.get("errors") or []), str(stored.get("marketSource") or "ledger stage-1 snapshot"), True
        country = country.upper()
        if self.lse_official.supported(country.upper(), spec.code):
            quotes, screening_errors, market_source = self.lse_official.batch_quotes(selected_universe, country.upper(), spec)
        elif self.nasdaq_nordic.supported(country.upper(), spec.code):
            quotes, screening_errors, market_source = self.nasdaq_nordic.batch_quotes(selected_universe, country.upper(), spec)
        elif self.b3_official.supported(country.upper(), spec.code):
            quotes, screening_errors, market_source = self.b3_official.batch_quotes(selected_universe, country.upper(), spec)
        elif self.bme_official.supported(country.upper(), spec.code):
            quotes, screening_errors, market_source = self.bme_official.batch_quotes(selected_universe, country.upper(), spec)
        elif self.bist_official.supported(country.upper(), spec.code):
            quotes, screening_errors, market_source = self.bist_official.batch_quotes(selected_universe, country.upper(), spec)
        elif self.us_screener.supported(country.upper(), spec.code):
            quotes, screening_errors, market_source = self.us_screener.batch_quotes(selected_universe, country.upper(), spec)
        elif self.xetra_delayed.supported(country.upper(), spec.code):
            try:
                quotes, screening_errors, market_source = self.xetra_delayed.batch_quotes(
                    selected_universe, country.upper(), spec
                )
            except GlobalProviderError as exc:
                # Deutsche Boerse's public delayed file service can briefly
                # advertise unavailable objects or reject downloads. Do not
                # turn that upstream outage into a total Germany scan failure.
                if self.eodhd_bulk is not None:
                    quotes, fallback_errors, fallback_source = self.eodhd_bulk.batch_quotes(
                        selected_universe, country.upper(), spec
                    )
                else:
                    quotes, fallback_errors = self._batch_quotes(
                        selected_universe, country.upper(), spec
                    )
                    fallback_source = "Twelve Data licensed batch market feed"
                # A successful configured fallback is still live market
                # data. Keep only errors from that fallback in the readiness
                # gate; preserve the official-source outage in the source label
                # instead of falsely blocking an otherwise complete scan.
                screening_errors = list(fallback_errors)
                market_source = (
                    f"{fallback_source} (fallback after Deutsche Boerse delayed-source outage: "
                    f"{str(exc)[:120]})"
                )
        elif self.euronext_live.supported(country.upper(), spec.code):
            quotes, screening_errors, market_source = self.euronext_live.batch_quotes(selected_universe, country.upper(), spec)
        elif self.eodhd_bulk is not None:
            quotes, screening_errors, market_source = self.eodhd_bulk.batch_quotes(selected_universe, country.upper(), spec)
        else:
            quotes, screening_errors = self._batch_quotes(selected_universe, country.upper(), spec)
            market_source = "Twelve Data licensed batch market feed"
        return quotes, screening_errors, market_source, False

    def _advance_queue(
        self,
        ledger: AnalysisLedger,
        selected_universe: list[GlobalCompany],
        quote_by_ticker: dict[str, dict],
        registry,
        *,
        screening_source: str,
        batch_limit: int,
        budget: float,
        top_n: int,
        reuse: bool,
        errors: list[str],
        market_source: str,
    ) -> tuple[list[dict], dict, list[dict]]:
        """Register the whole universe, analyze one bounded batch, report the ledger.

        Returns (compact deepResults rows, ledger summary, ranked BUY rows). The
        queue, not a liquidity cut-off, decides what is analyzed: PENDING
        companies are drained most-liquid-first and then every finished company
        is refreshed once it ages past ``BIAP_GLOBAL_ANALYSIS_REFRESH_HOURS``.
        """
        refresh_hours = float(os.environ.get("BIAP_GLOBAL_ANALYSIS_REFRESH_HOURS", "24"))
        ledger.sync_universe(selected_universe, quote_by_ticker, screening_source=screening_source)
        if not reuse:
            ledger.set_meta("stage1", {"errors": errors, "marketSource": market_source})
            ledger.set_meta("stage1_synced_at", datetime.now(timezone.utc).isoformat())
        by_ticker = {item.ticker.upper(): item for item in selected_universe}

        def analyze(company: GlobalCompany) -> dict:
            result = analyze_company(company, registry=registry)
            result["screening"] = quote_by_ticker.get(company.ticker.upper()) or ledger.quote_for(company.ticker.upper())
            return result

        batch = drain(
            ledger, analyze, batch_limit=batch_limit, time_budget_sec=budget, refresh_after_hours=refresh_hours,
            seed=self._seed_screening_quote, universe_by_ticker=by_ticker,
        )
        counts = ledger.counts(refresh_after_hours=refresh_hours)
        counts["lastBatch"] = {**batch, "batchLimit": batch_limit, "timeBudgetSec": budget, "currentRssMb": rss_mb()}
        counts["complete"] = counts["queued"] == 0 and counts["refreshDue"] == 0
        counts["definitions"] = {
            "discovered": "equities in the exchange universe",
            "screened": "equities with a usable stage-1 market quote",
            "queued": "PENDING or ANALYZING (waiting for deep analysis)",
            "deepAnalyzed": "equities with a completed deep-analysis run (any outcome)",
            "evidencePass": "evidence gates cleared (data quality only, NOT financial completeness)",
            "financiallyComplete": "all core statements and credit ratios present from official sources",
            "buyQualified": "BUY_CANDIDATE with evidence PASS",
        }
        buys = list(ledger.full_results(buys_only=True))
        recommendations = self.annotate_ranking(self._recommendations(buys, top_n), buys)
        cap = max(25, int(os.environ.get("BIAP_GLOBAL_PAYLOAD_DEEP_ROWS", "150")))
        rows = ledger.summaries(limit=cap)
        counts["evidenceSummary"] = self.evidence_summary(counts)
        counts["_marketPool"] = ledger.market_pool(limit=max(50, top_n * 8))
        counts["_gateCounts"] = ledger.ranking_gate_counts()
        counts["_buyAfterIssuer"] = len(self._recommendations(buys, max(1, len(buys))))
        counts["payloadRowsShown"] = len(rows)
        counts["payloadRowsNote"] = f"deepResults shows the top {cap} rows; GET /global/analysis-ledger lists every company with status, reason and source"
        return rows, counts, recommendations

    def scan(
        self,
        *,
        country: str,
        exchange: str,
        top_n: int = 10,
        discovery_limit: int = 5000,
        deep_limit: int = 25,
        time_budget_sec: Optional[float] = None,
    ) -> dict:
        """Screen the whole exchange, then advance its persistent analysis queue.

        ``deep_limit`` is the size of ONE analysis batch (how much work this
        call may do), not a cap on how many companies get analyzed: every
        eligible company stays in the ledger queue and is analyzed by later
        batches, surviving restarts. ``time_budget_sec`` bounds the batch so a
        phone request can never run into a proxy/Android timeout.
        """
        top_n = max(1, min(int(top_n), 50))
        discovery_limit = max(top_n, min(int(discovery_limit), 5000))
        batch_limit = max(1, min(int(deep_limit), 500))
        budget = float(time_budget_sec if time_budget_sec is not None else os.environ.get("BIAP_GLOBAL_BATCH_BUDGET_SEC", "240"))
        spec = get_exchange(country, exchange)

        if country.upper() == "IR":
            return self._scan_iran(exchange=spec.code, top_n=top_n, deep_limit=deep_limit)

        registry = build_registry()
        universe_provider = registry.universe(country, spec.code)
        universe_provider_id = str(getattr(universe_provider, "provider_id", "unknown"))
        upstream_universe = getattr(universe_provider, "upstream", universe_provider)
        authoritative_provider_id = str(getattr(upstream_universe, "provider_id", universe_provider_id))
        authority_allow = {item.strip().upper() for item in (os.environ.get("BIAP_GLOBAL_AUTHORITATIVE_UNIVERSE_MARKETS") or "").split(",") if item.strip()}
        market_key = f"{country.upper()}:{spec.code.upper()}"
        # Reference/demo catalogs are useful for search, but cannot prove the
        # exact regulated/native segment (e.g. XMIL also exposes GEM cross-listings).
        # A cached official exchange file remains authoritative because the cache
        # preserves the upstream identity and freshness metadata.
        universe_authoritative = authoritative_provider_id.startswith("official-") or market_key in authority_allow
        universe_source = authoritative_provider_id
        universe = list(universe_provider.list_instruments(country=country.upper(), exchange=spec.code))
        resolved_count = len(universe)
        snapshot_info_fn = getattr(universe_provider, "snapshot_info", None)
        universe_info = snapshot_info_fn(country=country.upper(), exchange=spec.code) if callable(snapshot_info_fn) else {}
        try:
            official_count = max(resolved_count, int((universe_info or {}).get("officialCount") or resolved_count))
        except (TypeError, ValueError):
            official_count = resolved_count
        discovered_count = official_count
        selected_universe = universe[:discovery_limit]
        partial = official_count > discovery_limit

        official_market_source = (
            self.euronext_live.supported(country.upper(), spec.code)
            or self.lse_official.supported(country.upper(), spec.code)
            or self.nasdaq_nordic.supported(country.upper(), spec.code)
            or self.b3_official.supported(country.upper(), spec.code)
            or self.bme_official.supported(country.upper(), spec.code)
            or self.bist_official.supported(country.upper(), spec.code)
            or self.us_screener.supported(country.upper(), spec.code)
            or self.xetra_delayed.supported(country.upper(), spec.code)
        )
        if not self.market_api_key and self.eodhd_bulk is None and not official_market_source:
            market_provider = registry.market(country, spec.code)
            cached_companies = market_provider.cached_companies(country=country.upper(), exchange=spec.code) if hasattr(market_provider, "cached_companies") else []
            allowed_tickers = {item.ticker.upper() for item in selected_universe}
            cached_quotes = self._cached_quotes(cached_companies, allowed_tickers)
            ranked = sorted(cached_quotes, key=self._screen_rank, reverse=True)
            ledger = AnalysisLedger(country, spec.code)
            deep_results, analysis, _unused = self._advance_queue(
                ledger, selected_universe, {row["ticker"]: row for row in cached_quotes}, registry,
                screening_source="stored market records only (diagnostic)", batch_limit=batch_limit,
                budget=budget, top_n=top_n, reuse=False, errors=[], market_source="stored market records only",
            )
            readiness = self._readiness(
                country=country.upper(), exchange=spec.code, universe_count=discovered_count,
                screened_count=len(cached_quotes), deep_results=deep_results, live_market_data=False,
                market_source="stored market records only", partial_universe=partial, screening_errors=[],
                universe_authoritative=universe_authoritative, universe_source=universe_source, analysis=analysis,
            )
            return {
                "status": "MARKET_DATA_REQUIRED" if not cached_quotes else "CACHED_REFERENCE_ONLY",
                "country": country.upper(),
                "exchange": spec.code,
                "mic": spec.mic,
                "requestedRecommendations": top_n,
                "recommendationCount": 0,
                "universeDiscovered": discovered_count,
                "universeResolved": resolved_count,
                "universeScreened": len(cached_quotes),
                "quotesUsable": len(cached_quotes),
                "deepAnalyzed": analysis["deepAnalyzed"],
                "analysisLedger": analysis,
                "screeningCoveragePct": readiness["marketCoveragePct"],
                "fundamentalCoveragePct": readiness["fundamentalCoveragePct"],
                "screeningErrors": ["Fresh full-exchange batch market data is unavailable. Stored records are diagnostic only and cannot produce a market ranking."],
                "recommendations": [],
                "deepResults": deep_results,
                "catalogOnly": not bool(cached_quotes),
                "cachedMarketData": bool(cached_quotes),
                "rankingEligible": False,
                "dataReadiness": readiness,
                "notes": "No Top Market result is emitted from stored records. Restore a complete live market source, then rescan the ordinary-equity universe.",
            }

        ledger = AnalysisLedger(country, spec.code)
        quotes, screening_errors, market_source, stage1_reused = self._stage_one_quotes(selected_universe, country, spec, ledger)
        quote_by_ticker = {row["ticker"]: row for row in quotes}
        deep_results, analysis, ranked_buys = self._advance_queue(
            ledger, selected_universe, quote_by_ticker, registry,
            screening_source=market_source, batch_limit=batch_limit, budget=budget, top_n=top_n,
            reuse=stage1_reused, errors=screening_errors, market_source=market_source,
        )
        readiness = self._readiness(
            country=country.upper(), exchange=spec.code, universe_count=discovered_count,
            screened_count=len(quotes), deep_results=deep_results, live_market_data=True,
            market_source=market_source, partial_universe=partial, screening_errors=screening_errors,
            universe_authoritative=universe_authoritative, universe_source=universe_source, analysis=analysis,
        )
        market_pool = analysis.pop("_marketPool", [])
        gate_counts = analysis.pop("_gateCounts", None)
        buy_after_issuer = analysis.pop("_buyAfterIssuer", len(ranked_buys))
        recommendations = ranked_buys if readiness["rankingEligible"] else []
        market_top10 = self.market_top10(market_pool, top_n) if readiness["rankingEligible"] else []
        gates = (
            self.ranking_gates(
                gate_counts, buy_after_issuer=buy_after_issuer,
                ranking_eligible=bool(readiness["rankingEligible"]), readiness_reasons=list(readiness.get("reasons") or []),
            ) if gate_counts else []
        )
        if readiness["rankingEligible"]:
            status = "COMPLETE_SCAN" if recommendations else "NO_RECOMMENDATION"
        else:
            status = "INSUFFICIENT_MARKET_COVERAGE"

        return {
            "status": status,
            "country": country.upper(),
            "exchange": spec.code,
            "mic": spec.mic,
            "requestedRecommendations": top_n,
            "recommendationCount": len(recommendations),
            "qualifiedBuyCount": buy_after_issuer if readiness["rankingEligible"] else 0,
            "rankingGroups": self.ranking_groups(gate_counts) if gate_counts and readiness["rankingEligible"] else {},
            "marketTop10": market_top10,
            "marketTop10Note": (
                "Highest score x confidence among evidence-PASS companies of any call; not a buy list. "
                "Qualified BUY (recommendations) is the subset that also cleared the BUY threshold."
                if readiness["rankingEligible"] else "Ranking not released for this market; no Market Top 10 is shown."
            ),
            "rankingGates": gates,
            "universeDiscovered": discovered_count,
            "universeResolved": resolved_count,
            "universeScreened": len(quotes),
            "quotesUsable": len(quotes),
            "deepAnalyzed": analysis["deepAnalyzed"],
            "analysisLedger": analysis,
            "evidenceSummary": analysis.get("evidenceSummary"),
            "rankingBasis": self.RANKING_BASIS,
            "screeningCoveragePct": readiness["marketCoveragePct"],
            "fundamentalCoveragePct": readiness["fundamentalCoveragePct"],
            "screeningErrors": screening_errors,
            "recommendations": recommendations,
            "deepResults": deep_results,
            "cachedMarketData": False,
            "rankingEligible": readiness["rankingEligible"],
            "dataReadiness": readiness,
            "notes": (
                "Ranking is released only when the ordinary-equity universe has broad fresh market coverage "
                "and the deep shortlist has sufficient official fundamental provenance. Stage 1 covers the exchange; "
                "Stage 2 applies all BIAP evidence and agent gates."
            ),
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
