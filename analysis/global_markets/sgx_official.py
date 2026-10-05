"""Official SGX stock universe from the exchange website securities API.

The SGX public securities page is backed by api.sgx.com. BIAP uses it only for
instrument identity/membership and keeps rows explicitly classified by SGX as
"type=stocks"; bonds, ETFs, warrants, certificates and other product families
are excluded.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import requests

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_SOURCE_URL = "https://api.sgx.com/securities/v1.1"
_PROVIDER_ID = "official-sgx-website-securities"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_PARAMS = (
    "nc,adjusted-vwap,b,bv,p,c,change_vs_pc,change_vs_pc_percentage,cx,cn,dp,dpc,"
    "du,ed,fn,h,iiv,iopv,lt,l,o,p_,pv,ptd,s,sv,trading_time,v_,v,vl,vwap,vwap-currency"
)


def parse_sgx_prices(payload: dict) -> list[GlobalCompany]:
    prices = ((payload or {}).get("data") or {}).get("prices") or []
    if not isinstance(prices, list):
        raise GlobalProviderError("SGX securities payload has no prices list")
    observed = datetime.now(timezone.utc).isoformat()
    result: list[GlobalCompany] = []
    seen: set[str] = set()
    for row in prices:
        if not isinstance(row, dict) or str(row.get("type") or "").strip().lower() != "stocks":
            continue
        ticker = str(row.get("nc") or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        name = str(row.get("cn") or "").strip() or ticker
        result.append(GlobalCompany(
            country="SG",
            exchange="SGX",
            currency="SGD",
            ticker=ticker,
            name=name,
            mic_code="XSES",
            instrument_type="Common Stock",
            raw_provider_fields={
                "official_universe": True,
                "trusted_official_equity": True,
                "sgx_security_type": str(row.get("type") or ""),
                "sgx_product_code": ticker,
            },
            sources=[SourceEvidence(
                provider=_PROVIDER_ID,
                source_type="official_exchange_universe",
                source_id=f"SGX:{ticker}",
                source_url=_SOURCE_URL,
                observed_at=observed,
                quality=1.0,
                notes="SGX website securities API; rows explicitly classified by SGX as stocks only.",
            )],
        ))
    if not result:
        raise GlobalProviderError("SGX official website API returned no stock rows")
    return result


class SGXOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = _PROVIDER_ID
    source_url = _SOURCE_URL

    def __init__(self, *, timeout: float = 35.0) -> None:
        self.timeout = max(8.0, float(timeout))
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) == ("SG", "SGX")

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"SGX official universe is not configured for {country}/{exchange}")
        try:
            response = requests.get(
                self.source_url,
                params={"excludetypes": "bonds", "params": _PARAMS},
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/json",
                    "Referer": "https://www.sgx.com/securities/securities-prices",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GlobalProviderError(f"SGX securities API request failed: {type(exc).__name__}") from exc
        meta = payload.get("meta") if isinstance(payload, dict) else {}
        if str((meta or {}).get("code") or "") != "200":
            raise GlobalProviderError(f"SGX securities API rejected request: {(meta or {}).get('message')}")
        result = parse_sgx_prices(payload)
        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0,
            "publicationDate": datetime.now(timezone.utc).date().isoformat(),
            "nativeMic": "XSES",
            "identitySource": "SGX public securities website API",
            "eligibleScope": "SGX type=stocks",
            "sourceUrl": self.source_url,
        }
        return result
