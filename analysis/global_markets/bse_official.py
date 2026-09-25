"""BSE active ordinary-equity universe from official daily bhavcopy files.

BSE's public full SCRIP.ZIP endpoint is not reliably current for automated
clients. The exchange does publish daily standardized equity bhavcopy ZIPs.
BIAP unions several recent official sessions so thinly traded but active
securities are retained, while stale/delisted instruments naturally disappear.

This is an active-tradable universe, not a claim that every suspended listed
security is present.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
import io
import zipfile
from typing import Optional

import requests

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_PROVIDER_ID = "official-bse-equity-bhavcopy"
_URL_TEMPLATE = "https://www.bseindia.com/download/BhavCopy/Equity/BSE_EQ_BHAVCOPY_{date}.ZIP"
_PAGE_URL = "https://www.bseindia.com/markets/MarketInfo/BhavCopy.aspx"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_EXCLUDED_NAME_TOKENS = (" REIT", "REIT ", "INVIT", " ETF", "ETF ", " FUND", "FUND ")
_EXCLUDED_SERIES = {"IF", "IT"}


def _parse_trade_date(value: str) -> Optional[date]:
    text = (value or "").strip()
    for fmt in ("%d-%b-%y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def parse_bse_bhavcopy_csv(text: str, *, source_url: str, observed_at: str) -> list[GlobalCompany]:
    rows = csv.DictReader(io.StringIO(text))
    result: list[GlobalCompany] = []
    for row in rows:
        ticker = (row.get("TckrSymb") or "").strip().upper()
        name = (row.get("FinInstrmNm") or ticker).strip()
        isin = (row.get("ISIN") or "").strip().upper()
        series = (row.get("SctySrs") or "").strip().upper()
        instrument_type = (row.get("FinInstrmTp") or "").strip().upper()
        if instrument_type != "Q":
            continue
        # Indian corporate equity ISINs use INE. This removes ETFs/mutual funds
        # (commonly INF), rights entitlements and debt-like instruments.
        if len(isin) != 12 or not isin.startswith("INE") or not isin.isalnum():
            continue
        if not ticker or ticker.endswith("#"):
            continue
        if series in _EXCLUDED_SERIES:
            continue
        upper_name = f" {name.upper()} "
        if any(token in upper_name for token in _EXCLUDED_NAME_TOKENS):
            continue
        trade_date = (row.get("TradDt") or "").strip()
        result.append(GlobalCompany(
            country="IN",
            exchange="BSE",
            currency="INR",
            ticker=ticker,
            name=name,
            mic_code="XBOM",
            isin=isin,
            instrument_type="Common Stock",
            raw_provider_fields={
                "official_universe": True,
                "trusted_official_equity": True,
                "bse_scrip_code": (row.get("FinInstrmId") or "").strip() or None,
                "bse_security_series": series or None,
                "bse_trade_date": trade_date or None,
                "bse_source": "standardized_equity_bhavcopy",
            },
            sources=[SourceEvidence(
                provider=_PROVIDER_ID,
                source_type="official_exchange_universe",
                source_id=f"BSE:{ticker}:{isin}",
                source_url=source_url,
                observed_at=observed_at,
                quality=0.98,
                notes="BSE official standardized equity bhavcopy; recent-session active universe.",
            )],
        ))
    return result


class BSEOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 25.0, target_sessions: int = 10, lookback_days: int = 28) -> None:
        self.timeout = max(8.0, float(timeout))
        self.target_sessions = max(3, int(target_sessions))
        self.lookback_days = max(self.target_sessions, int(lookback_days))
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) == ("IN", "BSE")

    def _download_session(self, day: date) -> tuple[list[GlobalCompany], Optional[date], str]:
        url = _URL_TEMPLATE.format(date=day.strftime("%d%m%Y"))
        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/zip,*/*",
                    "Referer": _PAGE_URL,
                },
                timeout=self.timeout,
            )
        except requests.RequestException:
            return [], None, url
        if response.status_code != 200 or response.content[:2] != b"PK":
            return [], None, url
        try:
            archive = zipfile.ZipFile(io.BytesIO(response.content))
            names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not names:
                return [], None, url
            body = archive.read(names[0])
            text = body.decode("utf-8-sig")
        except (zipfile.BadZipFile, KeyError, UnicodeDecodeError):
            return [], None, url
        observed = datetime.now(timezone.utc).isoformat()
        rows = parse_bse_bhavcopy_csv(text, source_url=url, observed_at=observed)
        session_date = None
        if rows:
            session_date = _parse_trade_date(str(rows[0].raw_provider_fields.get("bse_trade_date") or ""))
        return rows, session_date or day, url

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"BSE official universe is not configured for {country}/{exchange}")
        today = date.today()
        by_isin: dict[str, GlobalCompany] = {}
        sessions: list[date] = []
        urls: list[str] = []
        for offset in range(self.lookback_days + 1):
            rows, session_date, url = self._download_session(today - timedelta(days=offset))
            if not rows or session_date is None:
                continue
            sessions.append(session_date)
            urls.append(url)
            for row in rows:
                if row.isin and row.isin not in by_isin:
                    by_isin[row.isin] = row
            if len(sessions) >= self.target_sessions:
                break
        if not sessions or not by_isin:
            raise GlobalProviderError("BSE official bhavcopy returned no recent ordinary equities")
        latest = max(sessions)
        if (today - latest).days > 10:
            raise GlobalProviderError(f"BSE official bhavcopy is stale; latest session {latest.isoformat()}")
        result = sorted(by_isin.values(), key=lambda row: row.ticker.casefold())
        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0,
            "publicationDate": latest.isoformat(),
            "nativeMic": "XBOM",
            "identitySource": "BSE official standardized equity bhavcopy",
            "coverageBasis": f"union of {len(sessions)} recent trading sessions; active ordinary equities",
            "sessionDates": [value.isoformat() for value in sorted(set(sessions), reverse=True)],
            "sourceUrl": _PAGE_URL,
        }
        return result
