"""Official Abu Dhabi Securities Exchange quote/recent-history adapter.

ADX's public issuer pages call the exchange-owned API gateway. BIAP verifies
identity through securityOverview and consumes recentTrades for official OHLCV
history. The public endpoint currently exposes a short recent window, so BIAP
does not invent longer-horizon returns from it.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import requests

from .adx_fundamentals import _public_gateway_key
from .history_store import persist_daily_history
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, MarketDataProvider, append_source


_API_BASE = "https://apigateway.adx.ae"
_PAGE_BASE = "https://www.adx.ae/en/issuers/issuers-information/issuers-directory"
_PROVIDER_ID = "official-adx-company-market"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_ABU_DHABI = ZoneInfo("Asia/Dubai")


def _number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        result = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return result


def _observed_date(value: object) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            local = datetime.strptime(text, fmt).replace(tzinfo=_ABU_DHABI)
            return local.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def parse_adx_recent_trades(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        raise GlobalProviderError("ADX recent-trades response is not an object")
    response = payload.get("response")
    rows = response.get("results") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        raise GlobalProviderError("ADX recent-trades response has no results")
    parsed: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        date = str(row.get("date") or "").strip()
        close = _number(row.get("close"))
        if not date or close is None or close <= 0:
            continue
        parsed.append({
            "date": date,
            "open": _number(row.get("open")),
            "high": _number(row.get("high")),
            "low": _number(row.get("low")),
            "close": close,
            "volume": _number(row.get("volume")),
            "value": _number(row.get("value")),
            "trades": _number(row.get("trades")),
        })
    parsed.sort(key=lambda row: row["date"])
    if not parsed:
        raise GlobalProviderError("ADX recent-trades response has no valid price rows")
    return parsed


class ADXOfficialMarketProvider(MarketDataProvider):
    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 35.0) -> None:
        self.timeout = max(8.0, float(timeout))

    def _get(self, path: str) -> dict:
        key = _public_gateway_key(min(25.0, self.timeout))
        try:
            response = requests.get(
                _API_BASE + path,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/json",
                    "Channel-ID": "OSS WEB",
                    "Content-Type": "application/json",
                    "X-Correlation-ID": "biap-global-adx-market",
                    "adx-Gateway-APIKey": key,
                    "Referer": _PAGE_BASE,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GlobalProviderError(f"ADX market request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict) or str(payload.get("resultCode") or "").upper() != "S":
            raise GlobalProviderError("ADX market endpoint did not return success")
        return payload

    def enrich_market(self, company: GlobalCompany) -> GlobalCompany:
        if (company.country.upper(), company.exchange.upper()) != ("AE", "ADX"):
            raise GlobalProviderError(
                f"ADX official market provider is not configured for {company.country}/{company.exchange}"
            )
        symbol = company.ticker.strip().upper()
        if not symbol:
            raise GlobalProviderError("ADX official market provider requires a ticker")

        overview_payload = self._get(f"/adx/marketwatch/1.1/securityOverview/{symbol}")
        overview_response = overview_payload.get("response")
        overview = overview_response.get("overview") if isinstance(overview_response, dict) else None
        if not isinstance(overview, dict):
            raise GlobalProviderError("ADX securityOverview has no overview object")

        returned_symbol = str(overview.get("companySymbol") or "").strip().upper()
        if returned_symbol != symbol:
            raise GlobalProviderError(
                f"ADX market identity mismatch: requested {symbol}, returned {returned_symbol or 'none'}"
            )

        history_payload = self._get(f"/adx/marketwatch/1.1/recentTrades/{symbol}")
        rows = parse_adx_recent_trades(history_payload)
        latest = rows[-1]

        last = _number(overview.get("last")) or latest["close"]
        observed_at = _observed_date(latest["date"])
        if last is None or last <= 0 or not observed_at:
            raise GlobalProviderError(f"ADX returned no verified current quote for {symbol}")

        persist_daily_history(
            replace(company, currency="AED"),
            self.provider_id,
            (
                {
                    "date": row["date"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "adjusted_close": row["close"],
                    "volume": row["volume"],
                }
                for row in rows
            ),
            metadata={
                "source": "ADX recentTrades",
                "historyPoints": len(rows),
                "adjustment": "none-official-ohlcv",
            },
        )

        isin = str(overview.get("companyISIN") or "").strip().upper()
        if isin and (len(isin) != 12 or not isin.isalnum()):
            isin = ""

        enriched = replace(
            company,
            currency="AED",
            mic_code=company.mic_code or "XADS",
            isin=company.isin or isin or None,
            price=last,
            price_observed_at=observed_at,
            volume_today=_number(overview.get("volume")) or latest.get("volume"),
            market_cap=_number(overview.get("marketCap")),
            shares_outstanding=_number(overview.get("issuedShares")),
            price_52w_high=_number(overview.get("52weekHigh")),
            price_52w_low=_number(overview.get("52weekLow")),
            raw_provider_fields={
                **company.raw_provider_fields,
                "adx_market_source": "official_securityOverview_and_recentTrades",
                "adx_previous_close": _number(overview.get("previousClose")),
                "adx_open": _number(overview.get("open")),
                "adx_day_high": _number(overview.get("high")),
                "adx_day_low": _number(overview.get("low")),
                "adx_bid": _number(overview.get("bid")),
                "adx_ask": _number(overview.get("ask")),
                "adx_trading_state": str(overview.get("tradingState") or "").strip() or None,
                "adx_board": str(overview.get("boardId") or "").strip() or None,
                "adx_recent_history_points": len(rows),
                "adx_recent_history_start": rows[0]["date"],
                "adx_recent_history_end": rows[-1]["date"],
            },
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_exchange_market_history",
                source_id=f"ADX:{symbol}:{latest['date']}",
                source_url=f"https://www.adx.ae/en/issuers/issuers-information/issuers-directory/{symbol}",
                observed_at=observed_at,
                quality=1.0,
                notes=(
                    "Abu Dhabi Securities Exchange official securityOverview and recentTrades endpoints. "
                    "Current quote plus the exchange-published recent OHLCV window."
                ),
            ),
        )
