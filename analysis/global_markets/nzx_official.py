"""Authoritative NZX Main Board ordinary-equity universe.

NZX's official Main Board page is the membership source. Each current instrument
page exposes its security Type and Primary Listing Venue, allowing BIAP to keep
only primary New Zealand Ordinary Shares while excluding ETFs/funds and overseas
secondary listings. The result is cached daily by PersistentUniverseProvider.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
import re
from typing import Iterable, Optional

import requests

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_MARKET_URL = "https://www.nzx.com/markets/NZSX"
_INSTRUMENT_URL = "https://www.nzx.com/instruments/{ticker}"
_USER_AGENT = "BIAP Global NZX universe (+https://setai.no)"


def _visible_text(html: str) -> str:
    text = re.sub(r"(?is)<script\b.*?</script>", " ", html)
    text = re.sub(r"(?is)<style\b.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def parse_nzx_market_page(html: str) -> tuple[int, list[str]]:
    text = _visible_text(html)
    count_match = re.search(r"Instrument\s+Count\s*:?\s*(\d+)", text, flags=re.I)
    if not count_match:
        raise GlobalProviderError("NZX Main Board page has no instrument count")
    expected = int(count_match.group(1))
    codes = sorted(set(
        match.upper()
        for match in re.findall(
            r'href\s*=\s*["\']/instruments/([A-Za-z0-9.\-]+)["\']',
            html,
            flags=re.I,
        )
    ))
    if not codes:
        raise GlobalProviderError("NZX Main Board page has no instrument links")
    if len(codes) != expected:
        raise GlobalProviderError(
            f"NZX Main Board membership mismatch: page says {expected}, parsed {len(codes)}"
        )
    return expected, codes


def parse_nzx_instrument_page(html: str, *, ticker: str) -> dict:
    text = _visible_text(html)
    isin_match = re.search(r"ISIN\s*:?\s*([A-Z0-9]{12})", text, flags=re.I)
    type_match = re.search(
        r"Type\s*:?\s*(.*?)\s+52\s+Week\s+Change\s*:",
        text,
        flags=re.I,
    )
    primary_match = re.search(
        r"Primary\s+Listing\s+Venue\s*:?\s*(NZ|Overseas)\b",
        text,
        flags=re.I,
    )
    issuer_match = re.search(
        r"Issued\s+By\s*:?\s*(.*?)\s+ISIN\s*:",
        text,
        flags=re.I,
    )
    if not (isin_match and type_match and primary_match and issuer_match):
        raise GlobalProviderError(f"NZX instrument page could not be classified for {ticker}")
    return {
        "ticker": ticker.upper(),
        "name": issuer_match.group(1).strip(),
        "isin": isin_match.group(1).upper(),
        "type": type_match.group(1).strip(),
        "primaryListingVenue": primary_match.group(1),
    }


class NZXOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = "official-nzx-main-board"
    source_url = _MARKET_URL

    def __init__(self, *, timeout: float = 20.0, workers: int = 10) -> None:
        self.timeout = max(8.0, float(timeout))
        self.workers = max(2, min(int(workers), 16))
        self.last_metadata: dict = {}

    def _get(self, url: str) -> str:
        try:
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-NZ,en;q=0.9",
                },
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            raise GlobalProviderError(f"NZX request failed for {url}: {type(exc).__name__}") from exc

    def _detail(self, ticker: str) -> dict:
        return parse_nzx_instrument_page(
            self._get(_INSTRUMENT_URL.format(ticker=ticker)),
            ticker=ticker,
        )

    def list_instruments(
        self,
        *,
        country: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> Iterable[GlobalCompany]:
        if (country or "").upper() != "NZ" or (exchange or "").upper() != "NZX":
            raise GlobalProviderError("NZX universe requires NZ/NZX")

        expected_count, codes = parse_nzx_market_page(self._get(self.source_url))
        details: dict[str, dict] = {}
        failures: list[str] = []

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            jobs = {pool.submit(self._detail, code): code for code in codes}
            for job in as_completed(jobs):
                code = jobs[job]
                try:
                    details[code] = job.result()
                except Exception as exc:
                    failures.append(f"{code}:{type(exc).__name__}:{str(exc)[:120]}")

        # Never silently replace an authoritative snapshot with a partial crawl.
        if failures or len(details) != expected_count:
            raise GlobalProviderError(
                f"NZX official universe crawl incomplete: expected={expected_count} "
                f"resolved={len(details)} failures={failures[:8]}"
            )

        observed = datetime.now(timezone.utc).isoformat()
        result: list[GlobalCompany] = []
        excluded_by_type = 0
        excluded_overseas = 0

        for ticker in codes:
            row = details[ticker]
            if str(row["type"]).strip().lower() != "ordinary shares":
                excluded_by_type += 1
                continue
            if str(row["primaryListingVenue"]).strip().upper() != "NZ":
                excluded_overseas += 1
                continue
            result.append(GlobalCompany(
                country="NZ",
                exchange="NZX",
                currency="NZD",
                ticker=ticker,
                name=str(row["name"]),
                mic_code="XNZE",
                isin=str(row["isin"]),
                instrument_type="Common Stock",
                raw_provider_fields={
                    "official_universe": True,
                    "nzx_security_type": row["type"],
                    "nzx_primary_listing_venue": row["primaryListingVenue"],
                    "domestic_scope": "NZX Main Board Ordinary Shares with Primary Listing Venue NZ",
                },
                sources=[SourceEvidence(
                    provider=self.provider_id,
                    source_type="official_exchange_universe",
                    source_id=f"NZX:{ticker}:{row['isin']}",
                    source_url=_INSTRUMENT_URL.format(ticker=ticker),
                    observed_at=observed,
                    quality=1.0,
                    notes="NZX official Main Board; Ordinary Shares with Primary Listing Venue NZ only.",
                )],
            ))

        if not result:
            raise GlobalProviderError("NZX official universe returned no primary New Zealand ordinary shares")

        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0,
            "rawMainBoardInstrumentCount": expected_count,
            "excludedNonOrdinaryCount": excluded_by_type,
            "excludedOverseasPrimaryCount": excluded_overseas,
            "identitySource": "NZX official Main Board + instrument detail pages",
            "domesticScope": "Type Ordinary Shares + Primary Listing Venue NZ",
        }
        return result
