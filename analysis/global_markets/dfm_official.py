"""Official Dubai Financial Market active-equity universe.

DFM's public listed-securities page calls the exchange's own widgets API with
Command=FreshSecuritiesLists and securitytype=equities. BIAP keeps only active
DFM equity rows; Nasdaq Dubai rows and delisted securities are excluded.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import requests

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider

_SOURCE_URL = "https://api2.dfm.ae/web/widgets/v1/data"
_PAGE_URL = "https://www.dfm.ae/the-exchange/market-information/listed-securities"
_PROVIDER_ID = "official-dfm-fresh-securities"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"


def parse_dfm_equities(payload: object) -> list[GlobalCompany]:
    if not isinstance(payload, list):
        raise GlobalProviderError("DFM FreshSecuritiesLists response is not a list")
    observed = datetime.now(timezone.utc).isoformat()
    result: list[GlobalCompany] = []
    seen: set[str] = set()
    for row in payload:
        if not isinstance(row, dict):
            continue
        if str(row.get("Exchange") or "").strip().upper() != "DFM":
            continue
        if row.get("Active") is not True:
            continue
        if str(row.get("SecurityType") or "").strip().lower() != "equity":
            continue
        ticker = str(row.get("SecuritySymbol") or "").strip().upper()
        name = str(row.get("FullName") or "").strip()
        if not ticker or not name or ticker in seen:
            continue
        seen.add(ticker)
        result.append(GlobalCompany(
            country="AE",
            exchange="DFM",
            currency="AED",
            ticker=ticker,
            name=name,
            mic_code="XDFM",
            instrument_type="Common Stock",
            sector=str(row.get("Sector") or "").strip() or None,
            raw_provider_fields={
                "official_universe": True,
                "trusted_official_equity": True,
                "dfm_id": str(row.get("ID") or "").strip() or None,
                "dfm_security_type": row.get("SecurityType"),
                "dfm_active": True,
                "dfm_listing_date": row.get("ListingDate"),
                "dfm_listing_year": row.get("ListingYear"),
                "dfm_foreign_ownership_allowed": row.get("ForeignOwnershipAllowed"),
                "dfm_indexed_symbol": row.get("IndexedSymbol"),
            },
            sources=[SourceEvidence(
                provider=_PROVIDER_ID,
                source_type="official_exchange_universe",
                source_id=f"DFM:{ticker}",
                source_url=_PAGE_URL,
                observed_at=observed,
                quality=1.0,
                notes="DFM official listed-securities widgets API; active DFM equity rows only.",
            )],
        ))
    if not result:
        raise GlobalProviderError("DFM official equities response returned no active DFM equities")
    return result


class DFMOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = _PROVIDER_ID
    source_url = _SOURCE_URL

    def __init__(self, *, timeout: float = 35.0) -> None:
        self.timeout = max(8.0, float(timeout))
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) == ("AE", "DFM")

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"DFM official universe is not configured for {country}/{exchange}")
        try:
            response = requests.post(
                self.source_url,
                data={
                    "Command": "FreshSecuritiesLists",
                    "Language": "en",
                    "lang": "en",
                    "securitytype": "equities",
                },
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/json,text/plain,*/*",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": _PAGE_URL,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GlobalProviderError(f"DFM official equities request failed: {type(exc).__name__}") from exc
        result = parse_dfm_equities(payload)
        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0,
            "publicationDate": datetime.now(timezone.utc).date().isoformat(),
            "nativeMic": "XDFM",
            "identitySource": "DFM FreshSecuritiesLists official widgets API",
            "eligibleScope": "Exchange=DFM, Active=true, SecurityType=Equity",
            "sourceUrl": self.source_url,
        }
        return result
