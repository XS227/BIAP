"""Free delayed Xetra post-trade market data from Deutsche Boerse.

Deutsche Boerse publishes MiFIR Art. 13 delayed post-trade files for Xetra
through its public Market Data + Services file service. BIAP uses the daily
consolidated NDJSON gzip to seed stage-one price/liquidity for the authoritative
T7 domestic common-stock universe.

The file is already exchange-scoped. Instruments are joined by ISIN, which is
the stable identifier shared with the official T7 reference universe.
"""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import io
import json
import re
from typing import Iterable, Optional

import requests

from .country_packs import ExchangeSpec
from .models import GlobalCompany
from .providers import GlobalProviderError

_API = "https://mfs.deutsche-boerse.com/api/DETR-posttrade"
_DOWNLOAD = "https://mfs.deutsche-boerse.com/api/download"
_USER_AGENT = "BIAP Global Xetra delayed market adapter (+https://setai.no)"
_PROVIDER = "official-deutsche-boerse-xetra-delayed-posttrade"


def _float(value: object) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def aggregate_xetra_posttrade(
    compressed: bytes,
    instruments: Iterable[GlobalCompany],
) -> dict[str, dict]:
    """Aggregate one Xetra daily NDJSON gzip over the requested ISIN universe."""
    by_isin = {
        str(company.isin or "").strip().upper(): company
        for company in instruments
        if str(company.isin or "").strip()
    }
    stats: dict[str, dict] = {}
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
        for raw in stream:
            try:
                row = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if not isinstance(row, dict):
                continue
            isin = str(row.get("instrumentIdentificationCode") or "").strip().upper()
            if isin not in by_isin:
                continue
            if str(row.get("priceCurrency") or "").strip().upper() not in {"", "EUR"}:
                continue
            price = _float(row.get("price"))
            if price is None or price <= 0:
                continue

            # Modification/cancellation messages are not additive trading volume.
            # Keep only original/unmodified prints for liquidity aggregation.
            modification = str(row.get("mmtModificationInd") or "").strip().upper()
            normal = modification in {"", "-"}
            timestamp = str(
                row.get("tradingDateAndTime")
                or row.get("publicationDateAndTime")
                or ""
            ).strip()
            quantity = _float(row.get("quantity"))
            quantity = quantity if quantity is not None and quantity >= 0 else 0.0

            item = stats.setdefault(isin, {
                "lastTimestamp": "",
                "lastPrice": None,
                "volume": 0.0,
                "turnover": 0.0,
                "trades": 0,
                "venueOfExecution": None,
            })
            if normal:
                item["volume"] += quantity
                item["turnover"] += price * quantity
                item["trades"] += 1
                if not item["lastTimestamp"] or timestamp >= item["lastTimestamp"]:
                    item["lastTimestamp"] = timestamp
                    item["lastPrice"] = price
                    item["venueOfExecution"] = str(row.get("venueOfExecution") or "").strip() or None
            elif item["lastPrice"] is None:
                # A corrected print can still prove a fresh price exists, but it
                # must not inflate volume/turnover.
                item["lastTimestamp"] = timestamp
                item["lastPrice"] = price
                item["venueOfExecution"] = str(row.get("venueOfExecution") or "").strip() or None

    return stats


class DeutscheBoerseXetraDelayedClient:
    provider_id = _PROVIDER

    def __init__(self, *, timeout: float = 90.0) -> None:
        self.timeout = max(10.0, float(timeout))
        self._cached_daily: Optional[tuple[str, str, bytes]] = None

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) == ("DE", "XETRA")

    def _request(self, url: str, *, accept: str = "*/*") -> requests.Response:
        try:
            response = requests.get(
                url,
                headers={"User-Agent": _USER_AGENT, "Accept": accept},
                timeout=self.timeout,
                allow_redirects=True,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise GlobalProviderError(
                f"Deutsche Boerse delayed Xetra request failed: {type(exc).__name__}"
            ) from exc

    def _download_daily(self) -> tuple[str, str, bytes]:
        if self._cached_daily is not None:
            return self._cached_daily
        metadata_response = self._request(_API, accept="application/json,*/*")
        try:
            payload = metadata_response.json()
        except ValueError as exc:
            raise GlobalProviderError("Xetra delayed file service returned invalid metadata JSON") from exc
        files = payload.get("CurrentFiles") if isinstance(payload, dict) else None
        if not isinstance(files, list):
            raise GlobalProviderError("Xetra delayed file service returned no file list")
        daily = sorted(
            str(name) for name in files
            if "daily" in str(name).lower() and str(name).lower().endswith(".json.gz")
        )
        if not daily:
            raise GlobalProviderError("Xetra delayed file service has no daily consolidated file")
        filename = daily[-1]
        match = re.search(r"daily-(\d{4}-\d{2}-\d{2})\.json\.gz$", filename)
        quote_date = match.group(1) if match else datetime.now(timezone.utc).date().isoformat()
        source_url = f"{_DOWNLOAD}/{filename.lstrip('/')}"
        content = self._request(source_url, accept="application/gzip,*/*").content
        if len(content) < 1_000 or content[:2] != b"\x1f\x8b":
            raise GlobalProviderError("Xetra delayed daily file is not a valid gzip payload")
        self._cached_daily = (quote_date, source_url, content)
        return self._cached_daily

    def batch_quotes(
        self,
        instruments: Iterable[GlobalCompany],
        country: str,
        spec: ExchangeSpec,
    ) -> tuple[list[dict], list[str], str]:
        if not self.supported(country, spec.code):
            raise GlobalProviderError(
                f"Deutsche Boerse delayed Xetra source is not configured for {country}/{spec.code}"
            )
        selected = list(instruments)
        quote_date, source_url, compressed = self._download_daily()
        stats = aggregate_xetra_posttrade(compressed, selected)
        by_isin = {
            str(company.isin or "").strip().upper(): company
            for company in selected
            if str(company.isin or "").strip()
        }
        quotes: list[dict] = []
        for isin, item in stats.items():
            company = by_isin.get(isin)
            if company is None:
                continue
            price = _float(item.get("lastPrice"))
            if price is None or price <= 0:
                continue
            volume = max(0.0, float(item.get("volume") or 0.0))
            turnover = max(0.0, float(item.get("turnover") or 0.0))
            timestamp = str(item.get("lastTimestamp") or "").strip()
            quotes.append({
                "ticker": company.ticker.upper(),
                "price": price,
                "averageVolume": volume,
                "liquidityValue": turnover if turnover > 0 else price * volume,
                "rangePosition": None,
                "quoteDate": timestamp[:10] if timestamp else quote_date,
                "mic": company.mic_code or spec.mic,
                "provider": self.provider_id,
                "sourceUrl": source_url,
                "isin": isin,
                "trades": int(item.get("trades") or 0),
                "venueOfExecution": item.get("venueOfExecution"),
            })
        errors: list[str] = []
        if not quotes:
            errors.append("Deutsche Boerse delayed Xetra daily file returned no usable common-stock matches")
        return quotes, errors, f"Deutsche Boerse official Xetra delayed post-trade ({quote_date})"
