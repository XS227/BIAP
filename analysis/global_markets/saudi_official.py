"""Saudi Exchange ordinary-equity universe from official daily reports.

Saudi Exchange's CDN blocks the BIAP production host. The provider therefore
tries the official static report first and, only when the CDN denies the
request, uses r.jina.ai as a text transport for that same official URL. Source
provenance remains the Saudi Exchange report URL and relay use is explicit.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from html.parser import HTMLParser
import re
from typing import Optional

import requests

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_PROVIDER_ID = "official-saudi-exchange-daily-report"
_MAIN_URL = "https://www.saudiexchange.sa/Resources/Reports-v2/DetailedDaily_en.html"
_NOMU_URL = "https://www.saudiexchange.sa/Resources/Reports-v2/DetailedDailySme_en.html"
_RELAY_PREFIX = "https://r.jina.ai/http://www.saudiexchange.sa"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_EXCLUDED_TOKENS = ("REIT", " ETF", "ETF ", " FUND", "FUND ", "SUKUK", " BOND", "BOND ", "RIGHTS")


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        lower = tag.lower()
        if lower in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif lower == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def _market_date(text: str) -> Optional[date]:
    match = re.search(r"Market\s*Date\s*[:\-]?\s*(\d{4})[/-](\d{2})[/-](\d{2})", text, re.I)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _eligible(symbol: str, name: str) -> bool:
    if not re.fullmatch(r"\d{4,6}", symbol):
        return False
    upper = f" {name.upper()} "
    return bool(name.strip()) and not any(token in upper for token in _EXCLUDED_TOKENS)


def _rows_from_markdown(text: str) -> list[tuple[str, str]]:
    pos = text.lower().find("companies list")
    body = text[pos:] if pos >= 0 else text
    result: list[tuple[str, str]] = []
    for line in body.splitlines():
        raw = line.strip().strip("|").strip()
        if "|" not in raw:
            continue
        cols = [part.strip() for part in raw.split("|")]
        if len(cols) < 2:
            continue
        symbol, name = cols[0], cols[1]
        if _eligible(symbol, name):
            result.append((symbol, name))
    return result


def _rows_from_html(text: str) -> list[tuple[str, str]]:
    parser = _TableParser()
    parser.feed(text)
    result: list[tuple[str, str]] = []
    for cols in parser.rows:
        if len(cols) < 2:
            continue
        symbol, name = cols[0].strip(), cols[1].strip()
        if _eligible(symbol, name):
            result.append((symbol, name))
    return result


def parse_saudi_daily_report(text: str, *, market: str, source_url: str, observed_at: str, relayed: bool = False) -> tuple[list[GlobalCompany], Optional[date]]:
    report_date = _market_date(text)
    pairs = _rows_from_markdown(text)
    if not pairs:
        pairs = _rows_from_html(text)
    seen: set[str] = set()
    result: list[GlobalCompany] = []
    for symbol, name in pairs:
        if symbol in seen:
            continue
        seen.add(symbol)
        result.append(GlobalCompany(
            country="SA",
            exchange="SAUDI_EXCHANGE",
            currency="SAR",
            ticker=symbol,
            name=name,
            mic_code="XSAU",
            instrument_type="Common Stock",
            raw_provider_fields={
                "official_universe": True,
                "trusted_official_equity": True,
                "saudi_market": market,
                "report_date": report_date.isoformat() if report_date else None,
                "transport_relay": relayed,
            },
            sources=[SourceEvidence(
                provider=_PROVIDER_ID,
                source_type="official_exchange_universe",
                source_id=f"SAUDI:{market}:{symbol}",
                source_url=source_url,
                observed_at=observed_at,
                quality=0.96 if relayed else 1.0,
                notes=(
                    "Saudi Exchange official detailed daily report; delivered through text relay because exchange CDN blocks production IP."
                    if relayed
                    else "Saudi Exchange official detailed daily report."
                ),
            )],
        ))
    return result, report_date


class SaudiExchangeOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 45.0) -> None:
        self.timeout = max(10.0, float(timeout))
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) == ("SA", "SAUDI_EXCHANGE")

    def _fetch(self, official_url: str, market: str) -> tuple[list[GlobalCompany], Optional[date], bool]:
        observed = datetime.now(timezone.utc).isoformat()
        headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,*/*"}
        try:
            direct = requests.get(official_url, headers=headers, timeout=self.timeout)
            if direct.status_code == 200 and len(direct.text) > 5000:
                rows, report_date = parse_saudi_daily_report(
                    direct.text, market=market, source_url=official_url, observed_at=observed, relayed=False
                )
                if rows:
                    return rows, report_date, False
        except requests.RequestException:
            pass

        path = official_url.split("www.saudiexchange.sa", 1)[-1]
        relay_url = _RELAY_PREFIX + path
        try:
            response = requests.get(relay_url, headers={"User-Agent": _USER_AGENT}, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GlobalProviderError(f"Saudi Exchange report transport failed for {market}: {type(exc).__name__}") from exc
        rows, report_date = parse_saudi_daily_report(
            response.text, market=market, source_url=official_url, observed_at=observed, relayed=True
        )
        if not rows:
            raise GlobalProviderError(f"Saudi Exchange report contained no eligible {market} equities")
        return rows, report_date, True

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"Saudi official universe is not configured for {country}/{exchange}")
        main, main_date, main_relay = self._fetch(_MAIN_URL, "MAIN")
        nomu, nomu_date, nomu_relay = self._fetch(_NOMU_URL, "NOMU")
        report_dates = [value for value in (main_date, nomu_date) if value is not None]
        if not report_dates:
            raise GlobalProviderError("Saudi Exchange reports did not expose a report date")
        latest = max(report_dates)
        if (date.today() - latest).days > 10:
            raise GlobalProviderError(f"Saudi Exchange daily report is stale; latest {latest.isoformat()}")
        by_symbol = {row.ticker: row for row in [*main, *nomu]}
        result = sorted(by_symbol.values(), key=lambda row: row.ticker)
        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0,
            "publicationDate": latest.isoformat(),
            "nativeMic": "XSAU",
            "identitySource": "Saudi Exchange official Detailed Daily reports",
            "mainMarketCount": len(main),
            "nomuCount": len(nomu),
            "relayUsed": main_relay or nomu_relay,
            "sourceUrls": [_MAIN_URL, _NOMU_URL],
            "eligibleScope": "ordinary company equities in Main Market and Nomu; REIT/fund/debt/right rows excluded",
        }
        return result
