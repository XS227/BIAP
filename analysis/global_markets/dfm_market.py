"""Official Dubai Financial Market quote/history adapter.

DFM's public company pages call the exchange-owned widgets API. BIAP uses the
company-profile command to verify issuer/venue identity and the trading command
for the current quote plus the close-history series that DFM itself renders.
No vendor symbol mapping or third-party market data is involved.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import math
import statistics
from typing import Any, Optional
from zoneinfo import ZoneInfo

import requests

from .history_store import persist_daily_history
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, MarketDataProvider, append_source


_API_URL = "https://api2.dfm.ae/web/widgets/v1/data"
_PAGE_BASE = "https://www.dfm.ae/the-exchange/market-information/company"
_PROVIDER_ID = "official-dfm-company-market"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_DUBAI = ZoneInfo("Asia/Dubai")


def _number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text in {"-", "—"}:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> Optional[int]:
    number = _number(value)
    return int(number) if number is not None and number >= 0 else None


def _loads_response(response: requests.Response) -> dict:
    try:
        payload = json.loads(response.content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GlobalProviderError("DFM market endpoint returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise GlobalProviderError("DFM market response is not an object")
    return payload


def _chart_rows(payload: dict) -> list[tuple[datetime, float]]:
    raw = payload.get("ChartData")
    if not raw:
        return []
    try:
        rows = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        raise GlobalProviderError("DFM ChartData is invalid JSON") from exc
    if not isinstance(rows, list):
        raise GlobalProviderError("DFM ChartData is not a list")

    parsed: list[tuple[datetime, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        close = _number(row.get("currentIndex"))
        date_text = str(row.get("date") or "").strip()
        if close is None or close <= 0 or not date_text:
            continue
        parsed_dt: Optional[datetime] = None
        for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                parsed_dt = datetime.strptime(date_text, fmt).replace(tzinfo=_DUBAI)
                break
            except ValueError:
                continue
        if parsed_dt is None:
            continue
        parsed.append((parsed_dt, close))
    parsed.sort(key=lambda item: item[0])
    return parsed


def _annualized_volatility(closes: list[float]) -> Optional[float]:
    returns = [
        math.log(cur / prev)
        for prev, cur in zip(closes, closes[1:])
        if prev > 0 and cur > 0
    ]
    return statistics.stdev(returns) * math.sqrt(252.0) * 100.0 if len(returns) >= 2 else None


def _max_drawdown(closes: list[float]) -> Optional[float]:
    if not closes:
        return None
    peak = closes[0]
    worst = 0.0
    for close in closes:
        peak = max(peak, close)
        if peak > 0:
            worst = min(worst, (close - peak) / peak * 100.0)
    return worst


def _period_return(closes: list[float], trading_days: int) -> Optional[float]:
    if len(closes) < 2:
        return None
    index = max(0, len(closes) - 1 - trading_days)
    previous = closes[index]
    current = closes[-1]
    return (current / previous - 1.0) * 100.0 if previous > 0 and current > 0 else None


def _last_trade_observed_at(value: object) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            # DFM exposes date precision for LastTradeDate. Anchor to start of
            # that exchange-local date instead of inventing an intraday time.
            local = datetime.strptime(text, fmt).replace(tzinfo=_DUBAI)
            return local.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None


class DFMOfficialMarketProvider(MarketDataProvider):
    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 35.0) -> None:
        self.timeout = max(8.0, float(timeout))

    def _post(self, body: str) -> dict:
        try:
            response = requests.post(
                _API_URL,
                data=body,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": "https://www.dfm.ae/",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GlobalProviderError(f"DFM market request failed: {type(exc).__name__}") from exc
        return _loads_response(response)

    def enrich_market(self, company: GlobalCompany) -> GlobalCompany:
        if (company.country.upper(), company.exchange.upper()) != ("AE", "DFM"):
            raise GlobalProviderError(
                f"DFM official market provider is not configured for {company.country}/{company.exchange}"
            )
        symbol = company.ticker.strip().upper()
        if not symbol:
            raise GlobalProviderError("DFM official market provider requires a ticker")

        profile = self._post(
            f"Command=companyprofile&Language=en&lang=en&symbol={symbol}"
        )
        returned_symbol = str(profile.get("Symbol") or "").strip().upper()
        returned_market = str(profile.get("Market") or profile.get("Exchange") or "").strip().upper()
        instrument_type = str(profile.get("InstrumentType") or "").strip().casefold()
        if returned_symbol != symbol:
            raise GlobalProviderError(
                f"DFM profile identity mismatch: requested {symbol}, returned {returned_symbol or 'none'}"
            )
        if returned_market and returned_market != "DFM":
            raise GlobalProviderError(
                f"DFM profile venue mismatch for {symbol}: returned {returned_market}"
            )
        if instrument_type and instrument_type not in {"equities", "equity"}:
            raise GlobalProviderError(
                f"DFM profile instrument is not equity for {symbol}: {instrument_type}"
            )

        now_local = datetime.now(_DUBAI)
        start = now_local - timedelta(days=370)
        trading = self._post(
            "Command=SearchProfileTradingTab"
            "&Language=en&lang=en"
            f"&Company={symbol}"
            f"&toDate={now_local.strftime('%d/%m/%Y')}"
            f"&fromDate={start.strftime('%d/%m/%Y')}"
            "&Period=today"
        )

        chart = _chart_rows(trading)
        closes = [close for _, close in chart]
        price = (
            _number(trading.get("LastPrice"))
            or _number(trading.get("CurrentValue"))
            or _number(profile.get("LastPrice"))
            or _number(profile.get("CurrentValue"))
            or _number(profile.get("ClosingPrice"))
        )
        observed_at = (
            _last_trade_observed_at(trading.get("LastTradeDate"))
            or _last_trade_observed_at(profile.get("LastTradeDate"))
            or (chart[-1][0].astimezone(timezone.utc).isoformat() if chart else None)
        )
        if price is None or price <= 0:
            raise GlobalProviderError(f"DFM returned no verified current price for {symbol}")
        if not observed_at:
            raise GlobalProviderError(f"DFM returned no verified trade date for {symbol}")

        # DFM currently returns roughly one quarter of chart closes from this
        # public company endpoint even when a wider date range is requested.
        # Calculate only horizons actually covered; never extrapolate a 6M return.
        return_1m = _period_return(closes, 21) if len(closes) >= 22 else None
        return_3m = _period_return(closes, 63) if len(closes) >= 50 else None
        return_6m = _period_return(closes, 126) if len(closes) >= 127 else None

        if chart:
            persist_daily_history(
                replace(company, currency="AED"),
                self.provider_id,
                (
                    {
                        "timestamp": int(dt.timestamp()),
                        "high": None,
                        "low": None,
                        "close": close,
                        "adjusted_close": close,
                        "volume": None,
                    }
                    for dt, close in chart
                ),
                metadata={
                    "source": "DFM SearchProfileTradingTab",
                    "historyPoints": len(chart),
                    "adjustment": "none-official-close",
                },
            )

        source_url = f"{_PAGE_BASE}/{symbol}/trading"
        enriched = replace(
            company,
            currency="AED",
            mic_code=company.mic_code or "XDFM",
            instrument_type=company.instrument_type or "Common Stock",
            sector=company.sector or str(profile.get("Sector") or "").strip() or None,
            price=price,
            price_observed_at=observed_at,
            volume_today=_number(trading.get("Volume") or profile.get("Volume")),
            market_cap=_number(trading.get("MarketCap") or profile.get("MarketCap")),
            shares_outstanding=_integer(profile.get("IssuedShares")),
            price_52w_high=_number(trading.get("High52") or profile.get("High52")),
            price_52w_low=_number(trading.get("Low52") or profile.get("Low52")),
            volatility_annualized_pct=_annualized_volatility(closes),
            max_drawdown_pct=_max_drawdown(closes),
            return_1m_pct=return_1m,
            return_3m_pct=return_3m,
            return_6m_pct=return_6m,
            raw_provider_fields={
                **company.raw_provider_fields,
                "dfm_market_source": "official_widgets_company_profile_and_trading",
                "dfm_last_trade_date": trading.get("LastTradeDate") or profile.get("LastTradeDate"),
                "dfm_previous_close": _number(trading.get("PreviousClose") or profile.get("PreviousClose")),
                "dfm_open": _number(trading.get("OpenPrice") or profile.get("OpenPrice")),
                "dfm_day_high": _number(trading.get("High") or profile.get("High")),
                "dfm_day_low": _number(trading.get("Low") or profile.get("Low")),
                "dfm_bid": _number(trading.get("Bid") or profile.get("Bid")),
                "dfm_offer": _number(trading.get("Offer") or profile.get("Offer")),
                "dfm_history_points": len(chart),
                "dfm_history_start": chart[0][0].date().isoformat() if chart else None,
                "dfm_history_end": chart[-1][0].date().isoformat() if chart else None,
                "dfm_isin": str(profile.get("ISIN") or "").strip() or None,
            },
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_exchange_market_history",
                source_id=f"DFM:{symbol}:{trading.get('LastTradeDate') or profile.get('LastTradeDate')}",
                source_url=source_url,
                observed_at=observed_at,
                quality=1.0,
                notes=(
                    "Dubai Financial Market official public company profile/trading endpoint. "
                    "Current quote and available exchange-rendered close history; trade timestamp has date precision."
                ),
            ),
        )
