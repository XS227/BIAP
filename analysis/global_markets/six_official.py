"""Authoritative SIX Swiss ordinary-equity universe.

SIX publishes its equity issuer list through the same public JSON endpoint used
by the official List of Equity Issuers page. BIAP keeps Swiss primary ordinary
share lines only; foreign sponsored/secondary listings, participation
certificates and unknown share classes are excluded from the ranking universe.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

import requests

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_SOURCE_URL = "https://www.six-group.com/sheldon/equity_issuers/v1/equity_issuers.json"
_PAGE_URL = "https://www.six-group.com/en/market-data/shares/companies.html"
_USER_AGENT = "BIAP Global SIX universe (+https://setai.no)"

# SIX's stable machine-readable share-class codes are the authority. RS is a
# Registered Share and BS is a Bearer Share; both are ordinary equity. The
# public display label for BS is currently "***", so BIAP normalizes that label
# instead of treating it as unknown. PC (Participation Certificate) is excluded.
_ORDINARY_SHARE_CODES = {"RS", "BS"}
_ORDINARY_SHARE_NAMES = {
    "REGISTERED SHARE",
    "BEARER SHARE",
    "COMMON SHARE",
    "ORDINARY SHARE",
}

# Strictly verified US ADR ticker aliases used only to reach the issuer's SEC
# CompanyFacts record. Legal-name equality is still required by the SEC adapter.
_SEC_TICKER_ALIASES = {
    "NOVN": "NVS",  # Novartis AG
    "UBSG": "UBS",  # UBS Group AG
}


def _clean(value: object) -> str:
    return str(value or "").strip()


def parse_six_equity_items(items: Iterable[dict]) -> list[GlobalCompany]:
    observed = datetime.now(timezone.utc).isoformat()
    result: list[GlobalCompany] = []
    seen: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue
        country = _clean(item.get("country")).upper()
        if country != "CH":
            continue
        if item.get("primaryListing") is not True:
            continue
        platform = _clean(item.get("tradingPlatform")).upper()
        if platform != "XSWX":
            continue
        currency = _clean(item.get("tradingCurrency")).upper()
        if currency != "CHF":
            continue
        share_code = _clean(item.get("classOfShareCode")).upper()
        source_share_class = _clean(item.get("classOfShare"))
        if share_code:
            if share_code not in _ORDINARY_SHARE_CODES:
                continue
        elif source_share_class.upper() not in _ORDINARY_SHARE_NAMES:
            continue
        if item.get("secondLineReasonCode") not in (None, ""):
            continue
        share_class = (
            "Registered Share" if share_code == "RS"
            else "Bearer Share" if share_code == "BS"
            else source_share_class
        )

        ticker = _clean(item.get("valorSymbol")).upper()
        name = _clean(item.get("company"))
        isin = _clean(item.get("isin")).upper()
        if not ticker or not name or ticker in seen:
            continue
        if len(isin) != 12 or not isin.isalnum() or not isin.startswith("CH"):
            continue

        seen.add(ticker)
        result.append(GlobalCompany(
            country="CH",
            exchange="SIX",
            currency=currency,
            ticker=ticker,
            name=name,
            mic_code="XSWX",
            isin=isin,
            instrument_type="Common Stock",
            raw_provider_fields={
                "official_universe": True,
                "six_valor_number": item.get("valorNumber"),
                "six_class_of_share": share_class,
                "six_source_class_of_share": source_share_class,
                "six_class_of_share_code": share_code or None,
                "six_regulatory_standard": item.get("regulatoryStandard"),
                "six_primary_listing": True,
                "six_first_listing_date": item.get("firstListingDate"),
                "six_last_listing_date": item.get("lastListingDate"),
                "sec_ticker_alias": _SEC_TICKER_ALIASES.get(ticker),
                "domestic_scope": "SIX country CH + primary listing + ordinary share class",
            },
            sources=[SourceEvidence(
                provider="official-six-equity-issuers",
                source_type="official_exchange_universe",
                source_id=f"SIX:{ticker}:{isin}",
                source_url=_PAGE_URL,
                observed_at=observed,
                quality=1.0,
                notes="SIX official List of Equity Issuers; Swiss primary RS/BS ordinary-share lines only.",
            )],
        ))

    if not result:
        raise GlobalProviderError("SIX official issuer feed returned no Swiss primary ordinary shares")
    return result


class SIXOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = "official-six-equity-issuers"
    source_url = _SOURCE_URL

    def __init__(self, *, timeout: float = 40.0) -> None:
        self.timeout = max(10.0, float(timeout))
        self.last_metadata: dict = {}

    def list_instruments(
        self,
        *,
        country: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> Iterable[GlobalCompany]:
        if (country or "").upper() != "CH" or (exchange or "").upper() != "SIX":
            raise GlobalProviderError("SIX universe requires CH/SIX")
        try:
            response = requests.get(
                self.source_url,
                timeout=self.timeout,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/json,text/plain,*/*",
                    "Referer": _PAGE_URL,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GlobalProviderError(f"SIX issuer feed request failed: {type(exc).__name__}") from exc

        items = payload.get("itemList") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise GlobalProviderError("SIX issuer feed returned an unexpected payload")

        rows = parse_six_equity_items(items)
        ch_primary = [
            item for item in items
            if isinstance(item, dict)
            and _clean(item.get("country")).upper() == "CH"
            and item.get("primaryListing") is True
        ]
        self.last_metadata = {
            "officialCount": len(rows),
            "resolvedCount": len(rows),
            "resolutionCoveragePct": 100.0,
            "rawIssuerLineCount": len(items),
            "swissPrimaryLineCount": len(ch_primary),
            "identitySource": "SIX official List of Equity Issuers JSON",
            "domesticScope": "country CH + primary listing + SIX RS/BS ordinary-share codes",
        }
        return rows
