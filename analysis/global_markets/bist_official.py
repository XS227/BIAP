"""Official Borsa Istanbul listed-equity universe and daily stage-one quotes.

The public Borsa Istanbul Daily Bulletin (THB) is an exchange-published,
semicolon-delimited ZIP. BIAP keeps only spot-equity rows whose instrument group
is EQT and whose series code ends in .E. Warrants, certificates, ETFs, funds,
AOF rows and other bulletin instruments never enter the ordinary-share universe.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import BytesIO, StringIO
import csv
from typing import Iterable, Optional
import zipfile

import requests

from .country_packs import ExchangeSpec
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider

_BASE = "https://borsaistanbul.com/data/thb"
_USER_AGENT = "BIAP Global official BIST adapter (+https://setai.no)"
_MIC = "XIST"
_UNIVERSE_PROVIDER = "official-bist-daily-equity-universe"
_MARKET_PROVIDER = "official-bist-daily-equity-bulletin"


def _float(value: object) -> Optional[float]:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _int(value: object) -> int:
    number = _float(value)
    return int(number) if number is not None and number >= 0 else 0


def _date_text(value: object) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1254", "iso-8859-9"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("cp1254", errors="replace")


def parse_bist_bulletin_csv(content: bytes | str) -> list[dict]:
    """Normalize ordinary BIST equity rows from one official THB CSV."""
    text = content if isinstance(content, str) else _decode_csv(content)
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        raise GlobalProviderError("BIST bulletin CSV is too short")

    header_index = next(
        (
            index
            for index, line in enumerate(lines[:6])
            if "TRADE DATE;" in line
            and "INSTRUMENT SERIES CODE;" in line
            and "INSTRUMENT GROUP;" in line
        ),
        None,
    )
    if header_index is None:
        raise GlobalProviderError("BIST bulletin English header was not found")

    reader = csv.DictReader(StringIO("\n".join(lines[header_index:])), delimiter=";")
    rows: list[dict] = []
    seen: set[str] = set()
    for source in reader:
        group = str(source.get("INSTRUMENT GROUP") or "").strip().upper()
        series = str(source.get("INSTRUMENT SERIES CODE") or "").strip().upper()
        instrument_type = str(source.get("INSTRUMENT TYPE") or "").strip().upper()
        market = str(source.get("MARKET") or "").strip().upper()
        if group != "EQT" or not series.endswith(".E"):
            continue
        if instrument_type and instrument_type != "MSPOTEQT":
            continue
        if market and market != "MSPOT":
            continue
        ticker = series[:-2].strip()
        if not ticker or ticker in seen:
            continue

        quote_date = _date_text(source.get("TRADE DATE"))
        close = _float(source.get("CLOSING PRICE"))
        previous = _float(source.get("PREVIOUS LAST PRICE"))
        price = close if close is not None and close > 0 else previous
        volume = max(0.0, float(_float(source.get("TOTAL TRADED VOLUME")) or 0.0))
        turnover = max(0.0, float(_float(source.get("TOTAL TRADED VALUE")) or 0.0))

        rows.append({
            "ticker": ticker,
            "seriesCode": series,
            "name": str(source.get("INSTRUMENT NAME") or ticker).strip() or ticker,
            "quoteDate": quote_date,
            "price": price if price is not None and price > 0 else None,
            "close": close,
            "previousClose": previous,
            "open": _float(source.get("OPENING PRICE")),
            "high": _float(source.get("HIGHEST PRICE")),
            "low": _float(source.get("LOWEST PRICE")),
            "vwap": _float(source.get("VWAP")),
            "volume": volume,
            "turnover": turnover,
            "trades": _int(source.get("TOTAL NUMBER OF CONTRACTS")),
            "marketSegment": str(source.get("MARKET SEGMENT") or "").strip().upper() or None,
            "marketSubSegment": str(source.get("MARKET SUB SEGMENT") or "").strip().upper() or None,
            "market": market or None,
            "instrumentGroup": group,
            "instrumentType": instrument_type or None,
        })
        seen.add(ticker)

    if not rows:
        raise GlobalProviderError("BIST bulletin normalized no ordinary equity rows")
    return rows


class BISTOfficialDailyClient:
    provider_id = _MARKET_PROVIDER

    def __init__(self, *, timeout: float = 30.0, lookback_days: int = 8) -> None:
        self.timeout = max(5.0, float(timeout))
        self.lookback_days = max(1, min(int(lookback_days), 14))
        self._cached: Optional[tuple[str, str, list[dict]]] = None

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) == ("TR", "BIST")

    @staticmethod
    def bulletin_url(day: date) -> str:
        return f"{_BASE}/{day:%Y}/{day:%m}/thb{day:%Y%m%d}1.zip"

    def _download_latest(self) -> tuple[str, str, bytes]:
        session = requests.Session()
        session.headers.update({"User-Agent": _USER_AGENT, "Accept": "application/zip,*/*"})
        today = datetime.now(timezone.utc).date()
        last_error = "not found"
        for back in range(self.lookback_days):
            day = today - timedelta(days=back)
            url = self.bulletin_url(day)
            try:
                response = session.get(url, timeout=self.timeout, allow_redirects=True)
            except requests.RequestException as exc:
                last_error = f"{day}: {type(exc).__name__}"
                continue
            if response.status_code == 404:
                last_error = f"{day}: 404"
                continue
            try:
                response.raise_for_status()
            except requests.RequestException as exc:
                last_error = f"{day}: {type(exc).__name__}"
                continue
            if len(response.content) < 1_000 or response.content[:2] != b"PK":
                last_error = f"{day}: invalid ZIP payload"
                continue
            try:
                with zipfile.ZipFile(BytesIO(response.content)) as archive:
                    csv_name = next((name for name in archive.namelist() if name.lower().endswith(".csv")), None)
                    if not csv_name:
                        last_error = f"{day}: ZIP contains no CSV"
                        continue
                    return day.isoformat(), url, archive.read(csv_name)
            except zipfile.BadZipFile:
                last_error = f"{day}: bad ZIP"
                continue
        raise GlobalProviderError(f"BIST daily bulletin unavailable: {last_error}")

    def snapshot(self) -> tuple[str, str, list[dict]]:
        if self._cached is not None:
            return self._cached
        bulletin_date, url, content = self._download_latest()
        rows = parse_bist_bulletin_csv(content)
        self._cached = (bulletin_date, url, rows)
        return self._cached

    def batch_quotes(
        self,
        instruments: Iterable[GlobalCompany],
        country: str,
        spec: ExchangeSpec,
    ) -> tuple[list[dict], list[str], str]:
        if not self.supported(country, spec.code):
            raise GlobalProviderError(f"BIST official market data is not configured for {country}/{spec.code}")
        bulletin_date, url, rows = self.snapshot()
        by_ticker = {str(row["ticker"]).upper(): row for row in rows}
        quotes: list[dict] = []
        for company in instruments:
            row = by_ticker.get(company.ticker.upper())
            if row is None:
                continue
            price = _float(row.get("price"))
            if price is None or price <= 0:
                continue
            volume = max(0.0, float(row.get("volume") or 0.0))
            turnover = max(0.0, float(row.get("turnover") or 0.0))
            high = _float(row.get("high"))
            low = _float(row.get("low"))
            range_position = None
            if high is not None and low is not None and high > low:
                range_position = max(0.0, min(1.0, (price - low) / (high - low)))
            quotes.append({
                "ticker": company.ticker.upper(),
                "price": price,
                "averageVolume": volume,
                "liquidityValue": turnover if turnover > 0 else price * volume,
                "rangePosition": range_position,
                "quoteDate": row.get("quoteDate") or bulletin_date,
                "mic": _MIC,
                "provider": self.provider_id,
                "sourceUrl": url,
                "seriesCode": row.get("seriesCode"),
                "trades": row.get("trades"),
                "marketSegment": row.get("marketSegment"),
            })
        errors: list[str] = []
        if not quotes:
            errors.append("BIST official daily bulletin returned no usable ordinary-equity matches")
        return quotes, errors, f"Borsa Istanbul official Daily Bulletin ({bulletin_date})"


class BISTOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = _UNIVERSE_PROVIDER

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.client = BISTOfficialDailyClient(timeout=timeout)
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return BISTOfficialDailyClient.supported(country, exchange)

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"BIST official universe is not configured for {country}/{exchange}")
        bulletin_date, url, rows = self.client.snapshot()
        observed = datetime.now(timezone.utc).isoformat()
        result: list[GlobalCompany] = []
        for row in rows:
            ticker = str(row["ticker"]).upper()
            result.append(GlobalCompany(
                country="TR",
                exchange="BIST",
                currency="TRY",
                ticker=ticker,
                name=str(row.get("name") or ticker),
                mic_code=_MIC,
                instrument_type="Common Stock",
                raw_provider_fields={
                    "official_universe": True,
                    "bist_bulletin_date": bulletin_date,
                    "bist_series_code": row.get("seriesCode"),
                    "bist_market_segment": row.get("marketSegment"),
                    "bist_market_sub_segment": row.get("marketSubSegment"),
                    "bist_market": row.get("market"),
                    "bist_instrument_group": row.get("instrumentGroup"),
                    "bist_instrument_type": row.get("instrumentType"),
                },
                sources=[SourceEvidence(
                    provider=self.provider_id,
                    source_type="official_exchange_universe",
                    source_id=f"BIST:{bulletin_date}:{ticker}",
                    source_url=url,
                    observed_at=observed,
                    quality=1.0,
                    notes="Borsa Istanbul Daily Bulletin ordinary spot-equity row (EQT, .E series).",
                )],
            ))
        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0 if result else 0.0,
            "publicationDate": bulletin_date,
            "nativeMic": _MIC,
            "identitySource": "Borsa Istanbul official Daily Bulletin",
            "sourceUrl": url,
        }
        if not result:
            raise GlobalProviderError("BIST official bulletin returned an empty ordinary-equity universe")
        return result
