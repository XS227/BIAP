"""Authoritative EU regulated-equity universe from ESMA FIRDS.

FIRDS decides *membership*. A symbol resolver only adds the local ticker needed
by quote providers and the app. Resolver misses remain explicit through
``last_metadata.officialCount`` so downstream coverage never treats a mapped
subset as the whole market.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import os
import time
from typing import Optional
import xml.etree.ElementTree as ET
import zipfile

import requests

from .country_packs import ExchangeSpec, get_exchange
from .euronext_live import EuronextLiveRegulatedClient
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_SOLR = "https://registers.esma.europa.eu/solr/esma_registers_firds_files/select"
_OPENFIGI = "https://api.openfigi.com/v3/mapping"
_USER_AGENT = "BIAP Global FIRDS universe (+https://setai.no)"

# FIRDS native/relevant venue used for the regulated/native common-share market.
# Milan's operating MIC is XMIL while its regulated equity segment in current
# FIRDS records is MTAA; country_packs already accepts MTAA for Euronext Milan.
_NATIVE_MIC: dict[tuple[str, str], str] = {
    ("FR", "EURONEXT_PARIS"): "XPAR",
    ("IT", "EURONEXT_MILAN"): "MTAA",
    ("NL", "EURONEXT_AMSTERDAM"): "XAMS",
    ("BE", "EURONEXT_BRUSSELS"): "XBRU",
    ("IE", "EURONEXT_DUBLIN"): "XDUB",
    ("PT", "EURONEXT_LISBON"): "XLIS",
    ("NO", "EURONEXT_OSLO"): "XOSL",
    ("ES", "BME_MADRID"): "XMAD",
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(parent: Optional[ET.Element], name: str) -> Optional[ET.Element]:
    if parent is None:
        return None
    for node in list(parent):
        if _local(node.tag) == name:
            return node
    return None


def _text(parent: Optional[ET.Element], name: str) -> Optional[str]:
    node = _child(parent, name)
    value = (node.text or "").strip() if node is not None else ""
    return value or None


def parse_firds_refdata(elem: ET.Element) -> dict[str, Optional[str]]:
    """Extract one FIRDS RefData record without flattening repeated ``Id`` tags."""
    general = _child(elem, "FinInstrmGnlAttrbts")
    venue = _child(elem, "TradgVnRltdAttrbts")
    tech = _child(elem, "TechAttrbts")
    return {
        "isin": _text(general, "Id"),
        "fullName": _text(general, "FullNm"),
        "shortName": _text(general, "ShrtNm"),
        "cfi": _text(general, "ClssfctnTp"),
        "currency": _text(general, "NtnlCcy"),
        "issuerLei": _text(elem, "Issr"),
        "actualVenue": _text(venue, "Id"),
        "firstTradeDate": _text(venue, "FrstTradDt"),
        "relevantVenue": _text(tech, "RlvntTradgVn"),
        "competentAuthority": _text(tech, "RlvntCmptntAuthrty"),
    }


def is_native_common_share(record: dict[str, Optional[str]], *, spec: ExchangeSpec, native_mic: str) -> bool:
    """Return true only for native/relevant ordinary shares of the selected venue."""
    cfi = str(record.get("cfi") or "").upper()
    currency = str(record.get("currency") or "").upper()
    actual = str(record.get("actualVenue") or "").upper()
    relevant = str(record.get("relevantVenue") or "").upper()
    isin = str(record.get("isin") or "").upper()
    if not cfi.startswith("ES"):  # ISO 10962: Equity / Common-ordinary share
        return False
    if actual != native_mic.upper() or relevant != native_mic.upper():
        return False
    if spec.currencies and currency not in {value.upper() for value in spec.currencies}:
        return False
    if len(isin) != 12 or not isin.isalnum():
        return False
    return True


class ESMAFIRDSOpenFIGIUniverseProvider(InstrumentUniverseProvider):
    """Weekly FIRDS full universe with local ticker resolution through OpenFIGI."""

    provider_id = "official-esma-firds-universe"

    def __init__(
        self,
        *,
        timeout: float = 45.0,
        openfigi_api_key: Optional[str] = None,
    ) -> None:
        self.timeout = max(10.0, float(timeout))
        self.openfigi_api_key = (
            openfigi_api_key
            if openfigi_api_key is not None
            else os.environ.get("OPENFIGI_API_KEY")
        ) or ""
        self.openfigi_api_key = self.openfigi_api_key.strip()
        self.last_metadata: dict = {}
        self.euronext_directory = EuronextLiveRegulatedClient(timeout=self.timeout)

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) in _NATIVE_MIC

    def _get(self, url: str, *, params: Optional[dict] = None, accept: str = "*/*", timeout: Optional[float] = None) -> requests.Response:
        try:
            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": _USER_AGENT, "Accept": accept},
                timeout=timeout or self.timeout,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise GlobalProviderError(f"FIRDS request failed: {type(exc).__name__}") from exc

    def _latest_files(self) -> tuple[str, list[dict]]:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=21)
        response = self._get(
            _SOLR,
            params={
                "q": "*",
                "fq": f"publication_date:[{start.isoformat()}T00:00:00Z TO {today.isoformat()}T23:59:59Z]",
                "wt": "json",
                "rows": "2000",
            },
            accept="application/json",
        )
        try:
            docs = (response.json().get("response") or {}).get("docs") or []
        except (ValueError, AttributeError) as exc:
            raise GlobalProviderError("FIRDS file catalogue returned invalid JSON") from exc
        equity_files = [
            doc for doc in docs
            if isinstance(doc, dict)
            and str(doc.get("file_type") or "").upper() == "FULINS"
            and "FULINS_E_" in str(doc.get("file_name") or "").upper()
            and doc.get("download_link")
        ]
        if not equity_files:
            raise GlobalProviderError("No recent ESMA FIRDS FULINS equity full files found")
        equity_files.sort(
            key=lambda doc: (str(doc.get("publication_date") or ""), str(doc.get("file_name") or "")),
            reverse=True,
        )
        publication_date = str(equity_files[0].get("publication_date") or "")[:10]
        latest = sorted(
            [doc for doc in equity_files if str(doc.get("publication_date") or "")[:10] == publication_date],
            key=lambda doc: str(doc.get("file_name") or ""),
        )
        return publication_date, latest

    def _identities(self, *, country: str, exchange: str) -> tuple[str, list[dict]]:
        key = (country.upper(), exchange.upper())
        native_mic = _NATIVE_MIC.get(key)
        if not native_mic:
            raise GlobalProviderError(f"FIRDS native market mapping is not configured for {country}/{exchange}")
        spec = get_exchange(country, exchange)
        publication_date, files = self._latest_files()
        identities: dict[str, dict] = {}
        for doc in files:
            url = str(doc.get("download_link"))
            response = self._get(url, accept="application/zip", timeout=max(self.timeout, 120.0))
            try:
                archive = zipfile.ZipFile(io.BytesIO(response.content))
            except zipfile.BadZipFile as exc:
                raise GlobalProviderError("FIRDS equity full file is not a valid ZIP archive") from exc
            with archive:
                xml_name = next((name for name in archive.namelist() if name.lower().endswith(".xml")), None)
                if not xml_name:
                    raise GlobalProviderError("FIRDS equity ZIP contains no XML file")
                with archive.open(xml_name) as fh:
                    for _, elem in ET.iterparse(fh, events=("end",)):
                        if _local(elem.tag) != "RefData":
                            continue
                        record = parse_firds_refdata(elem)
                        if is_native_common_share(record, spec=spec, native_mic=native_mic):
                            identities[str(record["isin"])] = record
                        elem.clear()
        rows = list(identities.values())
        if not rows:
            raise GlobalProviderError(f"FIRDS returned no native common shares for {country}/{exchange}")
        return publication_date, rows

    def _openfigi_batch(self, session: requests.Session, jobs: list[dict]) -> list[dict]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }
        if self.openfigi_api_key:
            headers["X-OPENFIGI-APIKEY"] = self.openfigi_api_key
        for _ in range(8):
            try:
                response = session.post(_OPENFIGI, headers=headers, json=jobs, timeout=self.timeout)
            except requests.RequestException as exc:
                raise GlobalProviderError(f"OpenFIGI resolver request failed: {type(exc).__name__}") from exc
            if response.status_code == 429:
                try:
                    reset = int(float(response.headers.get("ratelimit-reset") or 3))
                except (TypeError, ValueError):
                    reset = 3
                time.sleep(max(2, min(reset + 1, 65)))
                continue
            try:
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise GlobalProviderError(f"OpenFIGI resolver rejected request: {type(exc).__name__}") from exc
            if not isinstance(payload, list) or len(payload) != len(jobs):
                raise GlobalProviderError("OpenFIGI resolver returned an unexpected payload")
            return payload
        raise GlobalProviderError("OpenFIGI rate limit did not recover")

    def _resolve_openfigi(self, identities: list[dict], *, native_mic: str) -> tuple[dict[str, dict], dict[str, str], dict[str, list[str]]]:
        resolved: dict[str, dict] = {}
        missing: dict[str, str] = {}
        ambiguous: dict[str, list[str]] = {}
        session = requests.Session()
        batch_size = 100 if self.openfigi_api_key else 5
        pause = 0.3 if self.openfigi_api_key else 2.6
        for start in range(0, len(identities), batch_size):
            batch = identities[start:start + batch_size]
            jobs = [
                {
                    "idType": "ID_ISIN",
                    "idValue": row["isin"],
                    "micCode": native_mic,
                    "marketSecDes": "Equity",
                }
                for row in batch
            ]
            results = self._openfigi_batch(session, jobs)
            for identity, result in zip(batch, results):
                isin = str(identity["isin"])
                data = result.get("data") if isinstance(result, dict) else None
                rows = [
                    row for row in (data or [])
                    if isinstance(row, dict)
                    and str(row.get("marketSector") or "").lower() == "equity"
                    and str(row.get("securityType2") or "").lower() == "common stock"
                ]
                tickers = sorted({str(row.get("ticker") or "").strip().upper() for row in rows if str(row.get("ticker") or "").strip()})
                if len(tickers) == 1:
                    ticker = tickers[0]
                    chosen = next(row for row in rows if str(row.get("ticker") or "").strip().upper() == ticker)
                    resolved[isin] = {
                        "ticker": ticker,
                        "figi": chosen.get("figi"),
                        "compositeFIGI": chosen.get("compositeFIGI"),
                        "shareClassFIGI": chosen.get("shareClassFIGI"),
                        "exchCode": chosen.get("exchCode"),
                        "name": chosen.get("name"),
                    }
                elif len(tickers) > 1:
                    ambiguous[isin] = tickers
                else:
                    missing[isin] = str((result or {}).get("warning") or (result or {}).get("error") or "no common-stock ticker")
            if start + batch_size < len(identities):
                time.sleep(pause)
        return resolved, missing, ambiguous

    def _resolve(self, identities: list[dict], *, native_mic: str):
        # Keep the historical internal signature so existing provider subclasses
        # and tests remain compatible. Country/exchange are unambiguously inferred
        # from the configured FIRDS native MIC.
        pair = next((key for key, mic in _NATIVE_MIC.items() if mic.upper() == native_mic.upper()), None)
        country, exchange = pair if pair else ("", "")
        resolved: dict[str, dict] = {}
        missing: dict[str, str] = {}
        ambiguous: dict[str, list[str]] = {}
        metadata: dict = {"directoryMatched": 0, "openfigiMatched": 0}

        unresolved_identities = identities
        if self.euronext_directory.supported(country, exchange):
            try:
                directory_resolved, directory_metadata = self.euronext_directory.resolve_isins(
                    identities, country=country, exchange=exchange
                )
                resolved.update(directory_resolved)
                metadata.update(directory_metadata)
                metadata["directoryMatched"] = len(directory_resolved)
                unresolved_identities = [
                    row for row in identities if str(row.get("isin") or "").upper() not in resolved
                ]
            except GlobalProviderError as exc:
                metadata["directoryError"] = str(exc)[:260]

        if unresolved_identities:
            figi_resolved, missing, figi_ambiguous = self._resolve_openfigi(
                unresolved_identities, native_mic=native_mic
            )
            for mapping in figi_resolved.values():
                mapping["resolver"] = "openfigi-ticker-resolver"
            resolved.update(figi_resolved)
            ambiguous.update(figi_ambiguous)
            metadata["openfigiMatched"] = len(figi_resolved)
        return resolved, missing, ambiguous, metadata

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"FIRDS universe is not configured for {country}/{exchange}")
        country = country.upper()
        exchange = exchange.upper()
        native_mic = _NATIVE_MIC[(country, exchange)]
        publication_date, identities = self._identities(country=country, exchange=exchange)
        resolution = self._resolve(identities, native_mic=native_mic)
        # Older/custom subclasses may still return the historical three-tuple.
        if len(resolution) == 3:
            resolved, missing, ambiguous = resolution
            resolver_metadata = {}
        else:
            resolved, missing, ambiguous, resolver_metadata = resolution
        official_count = len(identities)
        resolved_count = len(resolved)
        coverage = round(100.0 * resolved_count / official_count, 2) if official_count else 0.0
        self.last_metadata = {
            "officialCount": official_count,
            "resolvedCount": resolved_count,
            "resolutionCoveragePct": coverage,
            "publicationDate": publication_date,
            "nativeMic": native_mic,
            "identitySource": "ESMA FIRDS FULINS equity full files",
            "tickerResolver": "Euronext Live regulated directory + OpenFIGI fallback" if self.euronext_directory.supported(country, exchange) else "OpenFIGI",
            **resolver_metadata,
            "missingResolverCount": len(missing),
            "ambiguousResolverCount": len(ambiguous),
            "missingResolverSample": list(missing.items())[:20],
            "ambiguousResolverSample": list(ambiguous.items())[:20],
        }
        observed = datetime.now(timezone.utc).isoformat()
        result: list[GlobalCompany] = []
        for identity in identities:
            isin = str(identity["isin"])
            mapping = resolved.get(isin)
            if not mapping:
                continue
            ticker = str(mapping["ticker"])
            result.append(GlobalCompany(
                country=country,
                exchange=exchange,
                currency=str(identity.get("currency") or "EUR").upper(),
                ticker=ticker,
                name=str(identity.get("fullName") or identity.get("shortName") or mapping.get("name") or ticker),
                mic_code=native_mic,
                isin=isin,
                lei=str(identity.get("issuerLei") or "").strip().upper() or None,
                instrument_type="Common Stock",
                raw_provider_fields={
                    "official_universe": True,
                    "firds_publication_date": publication_date,
                    "firds_cfi": identity.get("cfi"),
                    "firds_actual_mic": identity.get("actualVenue"),
                    "firds_relevant_mic": identity.get("relevantVenue"),
                    "firds_competent_authority": identity.get("competentAuthority"),
                    "firds_first_trade_date": identity.get("firstTradeDate"),
                    "figi": mapping.get("figi"),
                    "composite_figi": mapping.get("compositeFIGI"),
                    "share_class_figi": mapping.get("shareClassFIGI"),
                    "openfigi_exchange_code": mapping.get("exchCode"),
                    "universe_resolution_coverage_pct": coverage,
                },
                sources=[
                    SourceEvidence(
                        provider=self.provider_id,
                        source_type="official_exchange_universe",
                        source_id=f"FIRDS:{isin}:{native_mic}",
                        source_url="https://registers.esma.europa.eu/solr/esma_registers_firds_files/select",
                        observed_at=observed,
                        quality=1.0,
                        notes=f"ESMA FIRDS {publication_date}; native common share where actualVenue == relevantVenue == {native_mic}.",
                    ),
                    SourceEvidence(
                        provider=str(mapping.get("resolver") or "openfigi-ticker-resolver"),
                        source_type="instrument_identifier_mapping",
                        source_id=str(mapping.get("figi") or isin),
                        source_url=(
                            "https://live.euronext.com/en/products/equities/regulated/list"
                            if mapping.get("resolver") == "official-euronext-live-regulated"
                            else "https://api.openfigi.com/v3/mapping"
                        ),
                        observed_at=observed,
                        quality=1.0 if mapping.get("resolver") == "official-euronext-live-regulated" else 0.9,
                        notes=(
                            "Official Euronext regulated-directory ISIN-to-symbol mapping; market membership remains defined by FIRDS."
                            if mapping.get("resolver") == "official-euronext-live-regulated"
                            else "Ticker resolution only; does not determine market membership."
                        ),
                    ),
                ],
            ))
        if not result:
            raise GlobalProviderError(f"FIRDS native universe resolved no local tickers for {country}/{exchange}")
        return result
