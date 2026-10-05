"""Official Abu Dhabi Securities Exchange listed-equity universe.

ADX's public website uses the exchange API gateway. BIAP uses the public issuer
directory endpoint only for identity/membership and keeps currently listed
equities on the Main Market (EQTY) and Growth Market (PRCN). Funds, ETFs, debt,
rights and delisted rows are excluded.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import requests

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_SOURCE_URL = "https://apigateway.adx.ae/adx/tradings/1.1/issuers"
_PAGE_URL = "https://www.adx.ae/en/issuers/issuers-information/issuers-directory"
_PROVIDER_ID = "official-adx-issuer-directory"
_PUBLIC_API_KEY = "1863a94c-582b-46f9-b4f0-0d02c0cc5307"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_EQUITY_MARKETS = {"EQTY", "PRCN"}


def parse_adx_issuers(payload: object) -> list[GlobalCompany]:
    if not isinstance(payload, dict):
        raise GlobalProviderError("ADX issuer response is not an object")
    response = payload.get("response")
    rows = response.get("issuers") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        raise GlobalProviderError("ADX issuer response has no issuers list")

    observed = datetime.now(timezone.utc).isoformat()
    result: list[GlobalCompany] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().upper()
        market = str(row.get("xMarketCode") or "").strip().upper()
        if status != "L" or market not in _EQUITY_MARKETS:
            continue
        ticker = str(row.get("dSymbol") or row.get("tradingCode") or row.get("eqCode") or "").strip().upper()
        name = str(row.get("nameEnglish") or "").strip()
        isin = str(row.get("isin") or "").strip().upper()
        if not ticker or not name or ticker in seen:
            continue
        if isin and (len(isin) != 12 or not isin.isalnum()):
            isin = ""
        seen.add(ticker)
        result.append(GlobalCompany(
            country="AE",
            exchange="ADX",
            currency="AED",
            ticker=ticker,
            name=name,
            mic_code="XADS",
            isin=isin or None,
            instrument_type="Common Stock",
            sector=str(row.get("sectorNameEnglish") or "").strip() or None,
            raw_provider_fields={
                "official_universe": True,
                "trusted_official_equity": True,
                "adx_market_code": market,
                "adx_market_id": str(row.get("marketCode") or "").strip() or None,
                "adx_status": status,
                "adx_sector_code": str(row.get("sectorCode") or "").strip() or None,
            },
            sources=[SourceEvidence(
                provider=_PROVIDER_ID,
                source_type="official_exchange_universe",
                source_id=f"ADX:{ticker}",
                source_url=_PAGE_URL,
                observed_at=observed,
                quality=1.0,
                notes="ADX official issuer directory; status=L and equity boards EQTY/PRCN only.",
            )],
        ))
    if not result:
        raise GlobalProviderError("ADX official issuer directory returned no listed equities")
    return result


class ADXOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = _PROVIDER_ID
    source_url = _SOURCE_URL

    def __init__(self, *, timeout: float = 35.0) -> None:
        self.timeout = max(8.0, float(timeout))
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) == ("AE", "ADX")

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"ADX official universe is not configured for {country}/{exchange}")
        try:
            response = requests.get(
                self.source_url,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/json",
                    "Channel-ID": "OSS WEB",
                    "Content-Type": "application/json",
                    "X-Correlation-ID": "biap-global",
                    "adx-Gateway-APIKey": _PUBLIC_API_KEY,
                    "Referer": _PAGE_URL,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GlobalProviderError(f"ADX official issuer request failed: {type(exc).__name__}") from exc

        result = parse_adx_issuers(payload)
        main_count = sum(1 for row in result if row.raw_provider_fields.get("adx_market_code") == "EQTY")
        growth_count = sum(1 for row in result if row.raw_provider_fields.get("adx_market_code") == "PRCN")
        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0,
            "publicationDate": datetime.now(timezone.utc).date().isoformat(),
            "nativeMic": "XADS",
            "identitySource": "ADX official issuer directory API",
            "eligibleScope": "status=L; xMarketCode in EQTY,PRCN",
            "mainMarketCount": main_count,
            "growthMarketCount": growth_count,
            "sourceUrl": self.source_url,
        }
        return result
