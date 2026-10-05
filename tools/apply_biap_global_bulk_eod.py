from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:140]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


EODHD_BULK = r'''"""Whole-exchange EOD market-data adapter for BIAP Global.

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
'''

GLOBAL_REFRESH = r'''"""Daily full-market scan refresher for BIAP Global."""
from __future__ import annotations

import json
import os

from .scan_service import _global_top_markets, scan_global_market


def main() -> int:
    has_eodhd = bool((os.environ.get("BIAP_EODHD_API_TOKEN") or "").strip())
    has_twelve = bool((os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "").strip())
    if not (has_eodhd or has_twelve):
        print("GLOBAL_SCAN_REFRESH: skipped; no full-exchange/batch market source configured")
        return 0

    deep_limit = max(10, min(int(os.environ.get("BIAP_GLOBAL_DAILY_DEEP_LIMIT", "50")), 100))
    summaries = []
    for country, exchange in _global_top_markets():
        try:
            result = scan_global_market(
                country=country,
                exchange=exchange,
                top_n=10,
                discovery_limit=5000,
                deep_limit=deep_limit,
            )
            summaries.append({
                "country": country,
                "exchange": exchange,
                "status": result.get("status"),
                "rankingEligible": result.get("rankingEligible"),
                "eligibleEquities": result.get("universeDiscovered"),
                "screenedEquities": result.get("universeScreened"),
                "marketCoveragePct": result.get("screeningCoveragePct"),
                "fundamentalCoveragePct": result.get("fundamentalCoveragePct"),
                "deepAnalyzed": result.get("deepAnalyzed"),
                "recommendationCount": result.get("recommendationCount"),
            })
        except Exception as exc:
            summaries.append({
                "country": country,
                "exchange": exchange,
                "status": "ERROR",
                "error": f"{type(exc).__name__}: {str(exc)[:260]}",
            })

    ready = sum(row.get("rankingEligible") is True for row in summaries)
    print(json.dumps({"markets": len(summaries), "ready": ready, "results": summaries}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

TEST_EODHD = r'''from global_markets.country_packs import get_exchange
from global_markets.eodhd_bulk import EODHDClient, EODHDBulkEODProvider
from global_markets.models import GlobalCompany


def test_exchange_code_resolves_by_mic():
    client = EODHDClient("test-token")
    client._exchange_rows = [
        {"Code": "PA", "OperatingMIC": "XPAR", "CountryISO2": "FR"},
        {"Code": "AS", "OperatingMIC": "XAMS", "CountryISO2": "NL"},
    ]
    assert client.exchange_code("FR", get_exchange("FR", "EURONEXT_PARIS")) == "PA"


def test_us_exchange_code_uses_specific_venue():
    client = EODHDClient("test-token")
    assert client.exchange_code("US", get_exchange("US", "NASDAQ")) == "NASDAQ"
    assert client.exchange_code("US", get_exchange("US", "NYSE")) == "NYSE"


def test_bulk_matches_vendor_class_separator_to_biap_ticker():
    provider = EODHDBulkEODProvider("test-token")
    provider.client._exchange_rows = [
        {"Code": "ST", "OperatingMIC": "XSTO", "CountryISO2": "SE"},
    ]
    provider.client._get_json = lambda path, params=None: [
        {"code": "HM-B.ST", "date": "2026-09-22", "close": 188.4, "volume": 1_200_000},
        {"code": "VOLV-B.ST", "date": "2026-09-22", "close": 301.1, "volume": 2_300_000},
    ]
    rows, errors, source = provider.batch_quotes(
        [
            GlobalCompany(country="SE", exchange="NASDAQ_STOCKHOLM", currency="SEK", ticker="HM.B", name="H&M"),
            GlobalCompany(country="SE", exchange="NASDAQ_STOCKHOLM", currency="SEK", ticker="VOLV.B", name="Volvo"),
        ],
        "SE",
        get_exchange("SE", "NASDAQ_STOCKHOLM"),
    )
    assert errors == []
    assert {row["ticker"] for row in rows} == {"HM.B", "VOLV.B"}
    assert all(row["quoteDate"] == "2026-09-22" for row in rows)
    assert "EODHD" in source
'''

Path("analysis/global_markets/eodhd_bulk.py").write_text(EODHD_BULK, encoding="utf-8")
Path("analysis/global_markets/global_scan_refresh.py").write_text(GLOBAL_REFRESH, encoding="utf-8")
Path("analysis/tests/test_global_eodhd_bulk.py").write_text(TEST_EODHD, encoding="utf-8")

# Scanner: use EODHD whole-exchange EOD when configured, then Twelve Data batch.
p = Path("analysis/global_markets/scanner.py")
text = p.read_text(encoding="utf-8")
old = "from .country_packs import ExchangeSpec, get_country_pack, get_exchange\n"
new = old + "from .eodhd_bulk import EODHDBulkEODProvider\n"
if new not in text:
    if old not in text:
        raise SystemExit("scanner import anchor missing")
    text = text.replace(old, new, 1)
old = '        self.market_api_key = (os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "").strip()\n'
new = (
    old
    + '        self.eodhd_api_token = (os.environ.get("BIAP_EODHD_API_TOKEN") or "").strip()\n'
    + '        self.eodhd_bulk = EODHDBulkEODProvider(self.eodhd_api_token, timeout=max(20.0, self.timeout)) if self.eodhd_api_token else None\n'
)
if new not in text:
    if old not in text:
        raise SystemExit("scanner key anchor missing")
    text = text.replace(old, new, 1)
text = text.replace(
    "        live_market_data: bool,\n        partial_universe: bool,\n",
    "        live_market_data: bool,\n        market_source: str,\n        partial_universe: bool,\n",
    1,
)
text = text.replace(
    '            "marketSource": "licensed live batch market feed" if live_market_data else "stored market records only",\n',
    '            "marketSource": market_source if live_market_data else "stored market records only",\n',
    1,
)
text = text.replace(
    '            reasons.append("live_batch_market_source_unavailable")\n',
    '            reasons.append("full_market_source_unavailable")\n',
    1,
)
text = text.replace(
    "        if not self.market_api_key:\n",
    "        if not self.market_api_key and self.eodhd_bulk is None:\n",
    1,
)
text = text.replace(
    "                screened_count=len(cached_quotes), deep_results=deep_results, live_market_data=False,\n                partial_universe=partial, screening_errors=[],\n",
    "                screened_count=len(cached_quotes), deep_results=deep_results, live_market_data=False,\n                market_source=\"stored market records only\", partial_universe=partial, screening_errors=[],\n",
    1,
)
old = '''        quotes, screening_errors = self._batch_quotes(selected_universe, country.upper(), spec)\n        quote_by_ticker = {row["ticker"]: row for row in quotes}\n'''
new = '''        if self.eodhd_bulk is not None:\n            quotes, screening_errors, market_source = self.eodhd_bulk.batch_quotes(selected_universe, country.upper(), spec)\n        else:\n            quotes, screening_errors = self._batch_quotes(selected_universe, country.upper(), spec)\n            market_source = "Twelve Data licensed batch market feed"\n        quote_by_ticker = {row["ticker"]: row for row in quotes}\n'''
if new not in text:
    if old not in text:
        raise SystemExit("scanner live quote anchor missing")
    text = text.replace(old, new, 1)
text = text.replace(
    "            screened_count=len(quotes), deep_results=deep_results, live_market_data=True,\n            partial_universe=partial, screening_errors=screening_errors,\n",
    "            screened_count=len(quotes), deep_results=deep_results, live_market_data=True,\n            market_source=market_source, partial_universe=partial, screening_errors=screening_errors,\n",
    1,
)
p.write_text(text, encoding="utf-8")

# Daily scan cache: one full-market refresh per day, not a fresh paid pull per tap.
replace_once(
    "analysis/global_markets/scan_service.py",
    "max_age_hours: float = 0.5,",
    "max_age_hours: float = 30.0,",
)

p = Path("analysis/global_routes.py")
text = p.read_text(encoding="utf-8")
text = text.replace(
    "    maxAgeHours: float = Field(default=0.5, ge=0, le=6)\n",
    "    maxAgeHours: float = Field(default=30.0, ge=0, le=36)\n",
    1,
)
old = '    market_configured = bool(os.environ.get("BIAP_GLOBAL_MARKET_API_KEY"))\n'
new = (
    '    twelve_data_configured = bool((os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "").strip())\n'
    '    eodhd_bulk_configured = bool((os.environ.get("BIAP_EODHD_API_TOKEN") or "").strip())\n'
    '    market_configured = twelve_data_configured or eodhd_bulk_configured\n'
)
if new not in text:
    if old not in text:
        raise SystemExit("status market_configured anchor missing")
    text = text.replace(old, new, 1)
text = text.replace(
    '        "licensedMarketFeedConfigured": market_configured,\n',
    '        "licensedMarketFeedConfigured": market_configured,\n        "twelveDataBatchConfigured": twelve_data_configured,\n        "eodhdBulkEodConfigured": eodhd_bulk_configured,\n',
    1,
)
text = text.replace(
    '        "marketProviderMode": "licensed-live-plus-persistent-cache" if market_configured else "public-eod-fallback-plus-persistent-cache",\n',
    '        "marketProviderMode": ("eodhd-whole-exchange-eod" if eodhd_bulk_configured else "twelve-data-batch" if twelve_data_configured else "public-eod-fallback-plus-persistent-cache"),\n',
    1,
)
p.write_text(text, encoding="utf-8")

replace_once(
    "mobile/src/lib/global-api.ts",
    "export async function scanGlobalTop10(topN = 10, maxAgeHours = 0.5): Promise<GlobalTop10Response> {",
    "export async function scanGlobalTop10(topN = 10, maxAgeHours = 30): Promise<GlobalTop10Response> {",
)
replace_once(
    "mobile/src/app/market.tsx",
    "scanGlobalTop10(10, 0.5)",
    "scanGlobalTop10(10, 30)",
)

# Replace biased hard-coded ticker warm list with daily complete-exchange scan.
p = Path("deploy/sync-global-sources.sh")
text = p.read_text(encoding="utf-8")
old = '''# Expand the daily public-EOD/history cache for a broader set of liquid\n# operating companies. This is market-history coverage only, not a recommendation\n# list. Failures never erase existing snapshots.\nif ! "$PY" -m global_markets.market_cache_warm; then\n  echo "MARKET_CACHE_WARM: refresh degraded; existing market history preserved" >&2\nfi\n'''
new = '''# Refresh the actual connected exchanges from the complete ordinary-equity\n# universe. This replaces the old hand-maintained famous-ticker warmer. The scan\n# cache is the daily market artifact used by This Market and Global Top 10.\nif ! "$PY" -m global_markets.global_scan_refresh; then\n  echo "GLOBAL_SCAN_REFRESH: refresh degraded; existing complete scan caches preserved" >&2\nfi\n'''
if new not in text:
    if old not in text:
        raise SystemExit("source sync market warm anchor missing")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

# Runtime config.
p = Path("analysis/.env.global.example")
text = p.read_text(encoding="utf-8")
anchor = "BIAP_GLOBAL_MARKET_API_KEY=\n"
insertion = (
    anchor
    + "\n# Preferred daily whole-exchange EOD source. One bulk request covers one exchange;\n"
    + "# BIAP intersects it with the ordinary-equity universe before ranking.\n"
    + "BIAP_EODHD_API_TOKEN=\n"
    + "BIAP_GLOBAL_DAILY_DEEP_LIMIT=50\n"
)
if insertion not in text:
    if anchor not in text:
        raise SystemExit("env market key anchor missing")
    text = text.replace(anchor, insertion, 1)
p.write_text(text, encoding="utf-8")

# Deployment passes the server-only bulk token when the repository secret exists.
p = Path(".github/workflows/setup-biap-global-server.yml")
text = p.read_text(encoding="utf-8")
old = '      MARKET_KEY: ${{ secrets.BIAP_GLOBAL_MARKET_API_KEY || secrets.TWELVE_DATA_API_KEY }}\n'
new = old + '      EODHD_TOKEN: ${{ secrets.BIAP_EODHD_API_TOKEN || secrets.EODHD_API_TOKEN }}\n'
if new not in text:
    if old not in text:
        raise SystemExit("deploy env anchor missing")
    text = text.replace(old, new, 1)
old = '              "BIAP_GLOBAL_MARKET_API_KEY": os.environ.get("MARKET_KEY", ""),\n'
new = old + '              "BIAP_EODHD_API_TOKEN": os.environ.get("EODHD_TOKEN", ""),\n'
if new not in text:
    if old not in text:
        raise SystemExit("deploy provider pair anchor missing")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")
