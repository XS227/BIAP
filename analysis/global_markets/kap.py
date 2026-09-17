"""Türkiye KAP official financial-summary fundamentals for BIAP Global.

KAP (Kamuyu Aydinlatma Platformu / Public Disclosure Platform) publishes public
company pages and selected financial-statement line items. BIAP uses the public
BIST-company directory to resolve a ticker to its KAP company page, then reads
only the latest completed annual column from KAP's official financial summary.

The summary page itself states that it is delayed and that later reports may
correct comparative columns. Accordingly this provider is high-quality official
regulatory evidence, but it does not claim to be a full XBRL filing parser. No
undocumented private API is used and no missing line item is inferred.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
import threading
import time
from typing import Optional
import unicodedata

import httpx

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source

KAP_BASE = "https://www.kap.org.tr"
KAP_BIST_COMPANIES = f"{KAP_BASE}/tr/bist-sirketler"


def _plain(value: object) -> str:
    text = str(value or "")
    return " ".join(text.replace("\xa0", " ").split())


def _ascii_upper(value: object) -> str:
    # Turkish dotted/dotless I needs explicit handling before upper-casing.
    # NFKD then removes accents such as â in "kâr" so fixed KAP labels can be
    # compared conservatively without adding fuzzy concept matching.
    text = _plain(value).replace("ı", "i").replace("İ", "I").upper()
    text = text.translate(str.maketrans({
        "Ç": "C", "Ğ": "G", "Ö": "O", "Ş": "S", "Ü": "U",
    }))
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _number(value: object) -> Optional[float]:
    text = _plain(value)
    if not text or text in {"-", "—"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = text.replace(" ", "")
    # KAP Turkish pages use dot thousands and comma decimals. Financial-summary
    # integers most often have dots only; treat dots as thousands in that case.
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[-+]?\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    text = re.sub(r"[^0-9+\-.]", "", text)
    try:
        result = float(text)
    except ValueError:
        return None
    if negative:
        result = -abs(result)
    return None if result != result else result


def _currency_scale(value: object) -> tuple[str, float]:
    text = _ascii_upper(value).replace(" ", "")
    if not text:
        return "TRY", 1.0
    match = re.search(r"(1000000|1000)?(?:TL|TRY)$", text)
    if not match:
        return "TRY", 1.0
    factor = float(match.group(1) or 1)
    return "TRY", factor


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.current_href: Optional[str] = None
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "a":
            self.current_href = dict(attrs).get("href")
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.current_href is not None:
            self.links.append((self.current_href, _plain(" ".join(self.current_text))))
            self.current_href = None
            self.current_text = []


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._rows: list[list[str]] = []
        self._row: Optional[list[str]] = None
        self._cell: Optional[list[str]] = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "table":
            if self._table_depth == 0:
                self._rows = []
            self._table_depth += 1
        elif self._table_depth and tag == "tr" and self._row is None:
            self._row = []
        elif self._table_depth and tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif self._cell is not None and tag in {"br", "p", "div"}:
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._table_depth and tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(_plain(" ".join(self._cell)))
            self._cell = None
        elif self._table_depth and tag == "tr" and self._row is not None:
            if any(cell for cell in self._row):
                self._rows.append(self._row)
            self._row = None
            self._cell = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0:
                if self._rows:
                    self.tables.append(self._rows)
                self._rows = []
                self._row = None
                self._cell = None


# Conservative labels from KAP's own summary tables. We deliberately do not use
# broad substring inference because similar Turkish labels can represent distinct
# IFRS concepts.
_LABEL_MAP = {
    "TOPLAM VARLIKLAR": "total_assets",
    "DONEN VARLIKLAR": "current_assets",
    "NAKIT VE NAKIT BENZERLERI": "cash_and_equivalents",
    "TOPLAM YUKUMLULUKLER": "total_liabilities",
    "KISA VADELI YUKUMLULUKLER": "current_liabilities",
    "TOPLAM OZKAYNAKLAR": "total_equity",
    "HASILAT": "revenue",
    "BRUT KAR (ZARAR)": "gross_profit",
    "TICARI FAALIYETLERDEN BRUT KAR (ZARAR)": "gross_profit",
    "ESAS FAALIYET KARI (ZARARI)": "operating_income",
    "NET DONEM KARI (ZARARI)": "net_income",
    "SURDURULEN FAALIYETLER DONEM KARI (ZARARI)": "net_income",
    "ISLETME FAALIYETLERINDEN NAKIT AKISLARI": "operating_cash_flow",
    "ISLETME FAALIYETLERINDEN ELDE EDILEN NAKIT AKISLARI": "operating_cash_flow",
}


def _annual_period_columns(rows: list[list[str]]) -> tuple[Optional[int], Optional[str], Optional[int], Optional[str]]:
    """Return (latest index/period, previous index/period) for annual YYYY/12 columns."""
    best: Optional[tuple[int, int, str]] = None
    previous: Optional[tuple[int, int, str]] = None
    for row in rows:
        found: list[tuple[int, int, str]] = []
        for index, cell in enumerate(row):
            match = re.fullmatch(r"(20\d{2})/12", _plain(cell))
            if match:
                found.append((int(match.group(1)), index, f"{match.group(1)}/12"))
        if not found:
            continue
        found.sort(reverse=True)
        candidate = found[0]
        if best is None or candidate[0] > best[0]:
            best = candidate
            previous = found[1] if len(found) > 1 else None
    if best is None:
        return None, None, None, None
    return best[1], best[2], previous[1] if previous else None, previous[2] if previous else None


def parse_kap_financial_summary(html: str) -> dict:
    parser = _TableParser()
    parser.feed(html)
    values: dict[str, float] = {}
    previous_values: dict[str, float] = {}
    annual_period: Optional[str] = None
    previous_period: Optional[str] = None
    report_scope: Optional[str] = None
    reporting_currency = "TRY"

    for rows in parser.tables:
        annual_index, table_period, previous_index, table_previous = _annual_period_columns(rows)
        if annual_index is None or table_period is None:
            continue
        scale = 1.0
        for row in rows:
            if not row:
                continue
            label = _ascii_upper(row[0])
            if label == "SUNUM PARA BIRIMI" and annual_index < len(row):
                reporting_currency, scale = _currency_scale(row[annual_index])
                break
        for row in rows:
            if not row or annual_index >= len(row):
                continue
            label = _ascii_upper(row[0])
            if label == "FINANSAL TABLO NITELIGI":
                scope = _ascii_upper(row[annual_index])
                if "KONSOLIDE OLMAYAN" in scope:
                    report_scope = "standalone"
                elif "KONSOLIDE" in scope:
                    report_scope = "consolidated"
                continue
            field = _LABEL_MAP.get(label)
            if not field:
                continue
            value = _number(row[annual_index])
            if value is not None and field not in values:
                values[field] = value * scale
                annual_period = max(annual_period or table_period, table_period)
            if previous_index is not None and previous_index < len(row):
                prev = _number(row[previous_index])
                if prev is not None and field not in previous_values:
                    previous_values[field] = prev * scale
                    previous_period = table_previous or previous_period

    if not values or annual_period is None:
        raise GlobalProviderError("KAP summary contains no supported completed annual financial statement")

    revenue = values.get("revenue")
    revenue_prev = previous_values.get("revenue")
    net_income = values.get("net_income")
    net_income_prev = previous_values.get("net_income")
    if revenue_prev not in (None, 0):
        values["revenue_prev"] = revenue_prev
        if revenue is not None:
            values["revenue_yoy_pct"] = (revenue / revenue_prev - 1.0) * 100.0
    if revenue not in (None, 0) and net_income is not None:
        values["net_margin_pct"] = net_income / revenue * 100.0
    if revenue_prev not in (None, 0) and net_income_prev is not None:
        values["net_margin_prev_pct"] = net_income_prev / revenue_prev * 100.0

    year = int(annual_period[:4])
    return {
        "metrics": values,
        "period": annual_period,
        "periodEnd": f"{year:04d}-12-31",
        "previousPeriod": previous_period,
        "reportScope": report_scope or "unknown",
        "currency": reporting_currency,
    }


class KAPFundamentalsProvider(FundamentalsProvider):
    provider_id = "kap-official-financial-summary"
    _lock = threading.Lock()
    _ticker_paths: dict[str, str] = {}
    _paths_loaded_at = 0.0

    def __init__(self, *, timeout: float = 15.0, directory_ttl_seconds: float = 6 * 3600) -> None:
        self.timeout = max(5.0, float(timeout))
        self.directory_ttl_seconds = max(300.0, float(directory_ttl_seconds))

    def _get(self, url: str) -> str:
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": "BIAP-Global/1.0 (+https://setai.no)", "Accept": "text/html,application/xhtml+xml"},
            ) as client:
                response = client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as exc:
            raise GlobalProviderError(f"KAP request failed: {type(exc).__name__}") from exc

    def _load_directory(self) -> dict[str, str]:
        now = time.monotonic()
        cls = type(self)
        with cls._lock:
            if cls._ticker_paths and now - cls._paths_loaded_at < self.directory_ttl_seconds:
                return dict(cls._ticker_paths)
            html = self._get(KAP_BIST_COMPANIES)
            parser = _LinkParser()
            parser.feed(html)
            mapping: dict[str, str] = {}
            for href, text in parser.links:
                if "/sirket-bilgileri/ozet/" not in href:
                    continue
                candidate = _ascii_upper(text)
                if re.fullmatch(r"[A-Z0-9 ]{1,24}", candidate) and any(ch.isalpha() for ch in candidate):
                    for ticker in candidate.split():
                        if 2 <= len(ticker) <= 12 and re.fullmatch(r"[A-Z0-9]+", ticker):
                            mapping.setdefault(ticker, href)
            if not mapping:
                raise GlobalProviderError("KAP BIST company directory could not be parsed")
            cls._ticker_paths = mapping
            cls._paths_loaded_at = now
            return dict(mapping)

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.upper() != "TR":
            raise GlobalProviderError(f"KAP provider is configured for TR, not {company.country}")
        ticker = _ascii_upper(company.ticker).replace(" ", "")
        directory = self._load_directory()
        profile_path = directory.get(ticker)
        if not profile_path:
            raise GlobalProviderError(f"ticker {ticker!r} was not found in KAP's official BIST company directory")
        slug = profile_path.split("/sirket-bilgileri/ozet/", 1)[-1].strip("/")
        if not slug:
            raise GlobalProviderError("KAP company path is malformed")
        financial_url = f"{KAP_BASE}/tr/sirket-finansal-bilgileri/{slug}"
        parsed = parse_kap_financial_summary(self._get(financial_url))
        metrics = parsed["metrics"]
        allowed = {
            "revenue", "revenue_prev", "revenue_yoy_pct", "gross_profit", "operating_income",
            "net_income", "net_margin_pct", "net_margin_prev_pct", "total_assets",
            "total_liabilities", "total_equity", "current_assets", "current_liabilities",
            "cash_and_equivalents", "operating_cash_flow",
        }
        kwargs = {key: metrics.get(key) for key in allowed if metrics.get(key) is not None}
        if not kwargs:
            raise GlobalProviderError("KAP annual summary has none of BIAP's supported financial metrics")
        observed_at = datetime.now(timezone.utc).isoformat()
        kwargs.update({
            "reporting_currency": parsed["currency"],
            "filing_period_end": parsed["periodEnd"],
            "filing_observed_at": observed_at,
            "report_scope": parsed["reportScope"],
            "raw_provider_fields": {
                **company.raw_provider_fields,
                "kap_financial_summary_url": financial_url,
                "kap_annual_period": parsed["period"],
                "kap_previous_annual_period": parsed["previousPeriod"],
                "kap_summary_delay_notice": True,
            },
        })
        enriched = replace(company, **kwargs)
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_regulatory_financial_statement",
            source_id=f"{ticker}:{parsed['period']}",
            source_url=financial_url,
            observed_at=observed_at,
            period_end=parsed["periodEnd"],
            quality=0.96,
            notes=(
                "Official KAP financial-summary page; latest completed annual column only. "
                "KAP states that summary data may be delayed and comparative corrections require the full filing."
            ),
        ))
