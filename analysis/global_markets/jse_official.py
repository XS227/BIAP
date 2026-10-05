"""Official JSE ordinary-share universe from the exchange ISIN full file.

JSE publishes a current Equities ISIN full-file ZIP on its Client Portal. The
current 2026 fixed-width record exposes the JSE security type and alpha code.
BIAP admits only ordinary-share classes (Ordinary/Nord/Aord/Bord) and excludes
unit trusts, ETFs, indices, baskets, preference shares and structured products.
"""
from __future__ import annotations

from datetime import datetime, timezone
import io
import re
from typing import Optional
import zipfile

import requests

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_SOURCE_URL = "https://clientportal.jse.co.za/Reports/Downloadable-Files/Download?filepath=ISIN%2FEquities%2Fisinfull_e.zip"
_PAGE_URL = "https://clientportal.jse.co.za/downloadable-files?RequestNode=/ISIN/Equities"
_PROVIDER_ID = "official-jse-equities-isin-full"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_ORDINARY_TYPES = {"ORDINARY", "NORD", "AORD", "BORD"}
_SEC_TICKER_ALIASES = {
    "SSW": "SBSW",
    "HAR": "HMY",
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_jse_isin_full(text: str) -> list[GlobalCompany]:
    observed = datetime.now(timezone.utc).isoformat()
    result: list[GlobalCompany] = []
    seen: set[str] = set()

    for raw in str(text or "").splitlines():
        line = raw.rstrip("\r\n")
        if len(line) < 230:
            continue
        isin = line[0:12].strip().upper()
        issuer = _clean(line[12:67])
        description = _clean(line[67:178])
        security_type = line[209:219].strip()
        alpha = line[219:227].strip().upper()
        version = line[227:230].strip()
        if security_type.upper() not in _ORDINARY_TYPES:
            continue
        if not alpha or not re.fullmatch(r"[A-Z0-9.-]{1,8}", alpha):
            continue
        if len(isin) != 12 or not isin.isalnum():
            continue
        if alpha in seen:
            continue
        seen.add(alpha)

        number_text = line[178:193].strip()
        try:
            shares = int(number_text) if number_text.isdigit() else None
        except ValueError:
            shares = None
        raw_currency = line[206:209].strip().upper()
        # The official file uses ZAC (South African cents) for exchange prices.
        # GlobalCompany normalizes currencies to ISO ZAR; Yahoo ZAc is scaled in
        # yahoo_chart.py to match this representation.
        currency = "ZAR" if raw_currency in {"ZAC", "ZAR"} else (raw_currency or "ZAR")
        old_isin = line[230:242].strip().upper() or None
        registration = _clean(line[242:262]) or None
        tax_number = _clean(line[262:274]) or None

        result.append(GlobalCompany(
            country="ZA",
            exchange="JSE",
            currency=currency,
            ticker=alpha,
            name=description or issuer or alpha,
            mic_code="XJSE",
            isin=isin,
            instrument_type="Common Stock",
            shares_outstanding=float(shares) if shares and shares > 0 else None,
            raw_provider_fields={
                "official_universe": True,
                "trusted_official_equity": True,
                "jse_issuer_name": issuer or None,
                "jse_security_type": security_type,
                "jse_instrument_version": version or None,
                "jse_old_isin": old_isin,
                "jse_registration_number": registration,
                "jse_tax_number": tax_number,
                "jse_file_currency": raw_currency or None,
                "sec_ticker_alias": _SEC_TICKER_ALIASES.get(alpha),
            },
            sources=[SourceEvidence(
                provider=_PROVIDER_ID,
                source_type="official_exchange_universe",
                source_id=f"JSE:{alpha}:{isin}",
                source_url=_SOURCE_URL,
                observed_at=observed,
                quality=1.0,
                notes=(
                    "JSE official Equities ISIN full file; ordinary-share security "
                    "types only (Ordinary/Nord/Aord/Bord)."
                ),
            )],
        ))

    if not result:
        raise GlobalProviderError("JSE official ISIN file returned no ordinary shares")
    return result


class JSEOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = _PROVIDER_ID
    source_url = _SOURCE_URL

    def __init__(self, *, timeout: float = 45.0) -> None:
        self.timeout = max(10.0, float(timeout))
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) == ("ZA", "JSE")

    def _download_text(self) -> str:
        try:
            response = requests.get(
                self.source_url,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/zip,*/*",
                    "Referer": _PAGE_URL,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GlobalProviderError(f"JSE ISIN full-file request failed: {type(exc).__name__}") from exc
        if len(response.content) < 50_000 or response.content[:2] != b"PK":
            raise GlobalProviderError("JSE ISIN full-file response is not a complete ZIP")
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                name = next((item for item in archive.namelist() if not item.endswith("/")), None)
                if not name:
                    raise GlobalProviderError("JSE ISIN ZIP is empty")
                body = archive.read(name)
        except zipfile.BadZipFile as exc:
            raise GlobalProviderError("JSE ISIN full-file ZIP is invalid") from exc
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return body.decode(encoding)
            except UnicodeDecodeError:
                continue
        return body.decode("latin-1", errors="replace")

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"JSE official universe is not configured for {country}/{exchange}")
        result = parse_jse_isin_full(self._download_text())
        type_counts: dict[str, int] = {}
        for row in result:
            kind = str(row.raw_provider_fields.get("jse_security_type") or "")
            type_counts[kind] = type_counts.get(kind, 0) + 1
        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0,
            "publicationDate": datetime.now(timezone.utc).date().isoformat(),
            "nativeMic": "XJSE",
            "identitySource": "JSE official Equities ISIN full file",
            "ordinarySecurityTypes": type_counts,
            "sourceUrl": self.source_url,
        }
        return result
