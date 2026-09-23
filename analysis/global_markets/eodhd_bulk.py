"""Whole-exchange EOD market-data adapter for BIAP Global.

This adapter is used for stage-one exchange screening. One bulk request retrieves
the latest EOD rows for an entire exchange; BIAP intersects those rows with its
ordinary-equity universe. Official/regulatory fundamentals remain separate and
continue to control the Evidence gate during stage-two deep analysis.
"""
from __future__ import annotations

from datetime import date
import re
from typing import Any, Iterable, Optional

import httpx

from .country_packs import ExchangeSpec
from .models import GlobalCompany
from .providers import GlobalProviderError


def _float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _compact_symbol(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _date(value: object) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


class EODHDClient:
    def __init__(self, token: str, *, base_url: str = "https://eodhd.com/api", timeout: float = 45.0) -> None:
        self.token = str(token or "").strip()
        if not self.token:
            raise GlobalProviderError("BIAP_EODHD_API_TOKEN is required for EODHD bulk EOD")
        self.base_url = base_url.rstrip("/")
        self.timeout = max(5.0, float(timeout))
        self._exchange_rows: Optional[list[dict]] = None

    def _get_json(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        query = {"api_token": self.token, **(params or {})}
        try:
            with httpx.Client(timeout=self.timeout, headers={"Accept": "application/json"}) as client:
                response = client.get(f"{self.base_url}/{path.lstrip('/')}", params=query)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"EODHD request failed for {path}: {type(exc).__name__}") from exc
        if isinstance(payload, dict) and (payload.get("error") or (payload.get("message") and not payload.get("data"))):
            message = str(payload.get("error") or payload.get("message") or "provider error")
            raise GlobalProviderError(f"EODHD rejected {path}: {message[:260]}")
        return payload

    def exchanges(self) -> list[dict]:
        if self._exchange_rows is None:
            payload = self._get_json("exchanges-list/")
            if not isinstance(payload, list):
                raise GlobalProviderError("EODHD exchanges-list returned an unexpected payload")
            self._exchange_rows = [row for row in payload if isinstance(row, dict)]
        return self._exchange_rows

    def exchange_code(self, country: str, spec: ExchangeSpec) -> str:
        # EODHD explicitly accepts individual US venue codes in the bulk API.
        if country.upper() == "US" and spec.code.upper() in {"NASDAQ", "NYSE"}:
            return spec.code.upper()

        accepted = {mic.upper() for mic in spec.accepted_mics if mic}
        candidates: list[tuple[int, str]] = []
        for row in self.exchanges():
            code = str(row.get("Code") or row.get("code") or "").strip().upper()
            if not code:
                continue
            iso2 = str(row.get("CountryISO2") or row.get("country_iso2") or "").strip().upper()
            operating = str(row.get("OperatingMIC") or row.get("operating_mic") or "")
            mics = {part.strip().upper() for part in re.split(r"[,; ]+", operating) if part.strip()}
            overlap = accepted & mics
            if not overlap:
                continue
            score = 100 + 20 * len(overlap)
            if iso2 == country.upper():
                score += 50
            if spec.mic and spec.mic.upper() in mics:
                score += 25
            candidates.append((score, code))
        if not candidates:
            raise GlobalProviderError(
                f"EODHD has no exchange mapping for {country.upper()}/{spec.code} MICs={sorted(accepted)}"
            )
        candidates.sort(reverse=True)
        return candidates[0][1]

    def bulk_eod(self, country: str, spec: ExchangeSpec) -> tuple[str, list[dict]]:
        code = self.exchange_code(country, spec)
        payload = self._get_json(
            f"eod-bulk-last-day/{code}",
            {"fmt": "json", "filter": "extended"},
        )
        if not isinstance(payload, list):
            raise GlobalProviderError(f"EODHD bulk EOD returned an unexpected payload for {code}")
        return code, [row for row in payload if isinstance(row, dict)]


class EODHDBulkEODProvider:
    provider_id = "eodhd-whole-exchange-eod"

    def __init__(self, token: str, *, timeout: float = 45.0) -> None:
        self.client = EODHDClient(token, timeout=timeout)

    @staticmethod
    def _row_symbol(row: dict, exchange_code: str) -> str:
        raw = str(
            row.get("code") or row.get("Code") or row.get("symbol") or row.get("Symbol") or ""
        ).strip().upper()
        suffix = "." + exchange_code.upper()
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
        return raw

    @staticmethod
    def _effective_volume(row: dict) -> Optional[float]:
        # Extended bulk output includes rolling average-volume fields. Accept
        # common field-name variants and fall back to the session volume.
        for key in (
            "avgvol_50d", "avgvol_50", "average_volume_50d", "average_volume_50",
            "avgvol_14d", "avgvol_14", "average_volume_14d", "average_volume_14",
            "avgvol_200d", "avgvol_200", "average_volume_200d", "average_volume_200",
            "volume",
        ):
            value = _float(row.get(key))
            if value is not None and value > 0:
                return value
        return None

    def batch_quotes(
        self,
        instruments: Iterable[GlobalCompany],
        country: str,
        spec: ExchangeSpec,
    ) -> tuple[list[dict], list[str], str]:
        selected = list(instruments)
        by_exact = {item.ticker.upper(): item for item in selected}
        by_compact: dict[str, list[GlobalCompany]] = {}
        for item in selected:
            by_compact.setdefault(_compact_symbol(item.ticker), []).append(item)

        exchange_code, rows = self.client.bulk_eod(country, spec)
        results: list[dict] = []
        seen: set[str] = set()
        for row in rows:
            vendor_symbol = self._row_symbol(row, exchange_code)
            if not vendor_symbol:
                continue
            company = by_exact.get(vendor_symbol)
            if company is None:
                matches = by_compact.get(_compact_symbol(vendor_symbol), [])
                company = matches[0] if len(matches) == 1 else None
            if company is None:
                continue
            ticker = company.ticker.upper()
            if ticker in seen:
                continue
            price = _float(
                row.get("adjusted_close") or row.get("adjustedClose") or row.get("close") or row.get("Close")
            )
            volume = self._effective_volume(row)
            if price is None or price <= 0 or volume is None or volume <= 0:
                continue
            quote_date = _date(row.get("date") or row.get("Date") or row.get("datetime"))
            results.append({
                "ticker": ticker,
                "price": price,
                "averageVolume": volume,
                "liquidityValue": price * volume,
                "rangePosition": None,
                "quoteDate": quote_date.isoformat() if quote_date else None,
                "mic": company.mic_code or spec.mic,
                "provider": self.provider_id,
                "vendorExchange": exchange_code,
            })
            seen.add(ticker)

        errors: list[str] = []
        if not results:
            errors.append(f"EODHD bulk EOD returned no usable ordinary-equity matches for {country}/{spec.code}")
        return results, errors, f"EODHD whole-exchange EOD ({exchange_code})"
