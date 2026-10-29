"""Stage-one GB quotes from Yahoo Finance daily closes when the LSE API is unreachable.

Only the price source is replaced. The universe stays the stored official LSE
snapshot and filings stay official. Every quote and the market-source label say
``vendor: Yahoo Finance`` so the lower-trust price is never shown as official.
``quoteDate`` is the date of the last completed daily bar, so the 7-day price
freshness gate accepts a recent vendor close and rejects an old one. Nothing is
written to disk (no daily-history persistence).
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Iterable

from .country_packs import ExchangeSpec
from .models import GlobalCompany
from .providers import GlobalProviderError
from .yahoo_chart import YahooChartMarketProvider

VENDOR_LABEL = "vendor: Yahoo Finance"


def _default_provider() -> YahooChartMarketProvider:
    return YahooChartMarketProvider()


def _bars(result: dict, scale: float) -> list[dict[str, Any]]:
    quote_rows = ((result.get("indicators") or {}).get("quote") or [{}])
    row = quote_rows[0] if quote_rows and isinstance(quote_rows[0], dict) else {}
    closes, highs, lows, vols = (row.get(k) or [] for k in ("close", "high", "low", "volume"))
    bars = []
    for i, ts in enumerate(result.get("timestamp") or []):
        close = YahooChartMarketProvider._float(closes[i]) if i < len(closes) else None
        if close is None or close <= 0:
            continue
        high = YahooChartMarketProvider._float(highs[i]) if i < len(highs) else None
        low = YahooChartMarketProvider._float(lows[i]) if i < len(lows) else None
        vol = YahooChartMarketProvider._float(vols[i]) if i < len(vols) else None
        bars.append({"ts": ts, "close": close * scale,
                     "high": high * scale if high else None, "low": low * scale if low else None, "volume": vol})
    return bars


def quote_from_chart(company: GlobalCompany, payload: dict, spec: ExchangeSpec, provider: YahooChartMarketProvider) -> dict:
    results = (payload.get("chart") or {}).get("result")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise GlobalProviderError("no chart result")
    result = results[0]
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    _, scale = provider._validate_identity(company, meta)
    bars = _bars(result, scale)
    if not bars:
        raise GlobalProviderError("no verified close prices")
    # A bar still forming during the regular session is not a close.
    if len(bars) > 1 and provider._latest_bar_is_partial(meta, bars[-1]["ts"]):
        bars = bars[:-1]
    latest = bars[-1]
    observed = provider._observed_at(latest["ts"])
    if not observed:
        raise GlobalProviderError("no valid price timestamp")
    highs = [b["high"] for b in bars if b["high"]]
    lows = [b["low"] for b in bars if b["low"]]
    vols = [b["volume"] for b in bars[-30:] if b["volume"] is not None and b["volume"] >= 0]
    avg_vol = sum(vols) / len(vols) if vols else 0.0
    price = float(latest["close"])
    range_position = None
    if highs and lows and max(highs) > min(lows):
        range_position = max(0.0, min(1.0, (price - min(lows)) / (max(highs) - min(lows))))
    return {
        "ticker": company.ticker.upper(),
        "price": price,
        "averageVolume": avg_vol,
        "liquidityValue": price * avg_vol if avg_vol > 0 else price,
        "rangePosition": range_position,
        "quoteDate": observed[:10],
        "quoteDateBasis": "verified_completed_bar",
        "mic": company.mic_code or spec.mic,
        "provider": provider.provider_id,
        "priceSource": VENDOR_LABEL,
        "sourceUrl": f"https://finance.yahoo.com/quote/{provider._vendor_symbol(company)}",
        "isin": company.isin,
        "marketCap": None,
        "rankMetric": "traded_value",
    }


def yahoo_batch_quotes(
    instruments: Iterable[GlobalCompany],
    spec: ExchangeSpec,
    *,
    reason: str,
    provider: YahooChartMarketProvider | None = None,
    deadline_s: float | None = None,
) -> tuple[list[dict], list[str], str]:
    provider = provider or _default_provider()
    deadline_s = float(os.environ.get("BIAP_GB_VENDOR_DEADLINE_S", "540")) if deadline_s is None else deadline_s
    started = time.monotonic()
    quotes: list[dict] = []
    failed = 0
    skipped = 0
    first_error = ""
    for company in instruments:
        if time.monotonic() - started > deadline_s:
            skipped += 1
            continue
        try:
            quotes.append(quote_from_chart(company, provider._get(provider._vendor_symbol(company)), spec, provider))
        except GlobalProviderError as exc:
            failed += 1
            first_error = first_error or f"{company.ticker}: {str(exc)[:120]}"
    # Partial failures are not screening errors: the scanner's market-coverage threshold already decides whether
    # enough of the universe was priced. They are reported in the source label instead.
    errors: list[str] = []
    if not quotes:
        errors.append(f"{VENDOR_LABEL} returned no usable GB closes ({first_error or 'no instruments'})")
    dates = sorted({q["quoteDate"] for q in quotes})
    gaps = (f"; {failed} symbols failed, {skipped} not tried before the {deadline_s:.0f}s deadline"
            + (f" (first: {first_error})" if first_error else "")) if failed or skipped else ""
    label = (f"{VENDOR_LABEL} daily closes ({dates[-1] if dates else 'n/a'}); LSE official price source "
             f"unavailable: {reason[:120]}{gaps}")
    return quotes, errors, label
