"""Current KAP financial-summary adapter for BIAP Global.

KAP's public company financial-summary page currently streams its table rows in
Next.js Flight payloads. The older semantic-table parser is retained in kap.py;
this module adds a conservative fallback that reads only exact KAP labels and
explicit YYYY/12 cells from those server-rendered payloads. It does not call an
undocumented API and it never fuzzy-matches accounting concepts.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import html as html_lib
import json
import re
from typing import Optional

from .kap import (
    KAP_BASE,
    KAPFundamentalsProvider,
    _LABEL_MAP,
    _ascii_upper,
    _currency_scale,
    _number,
    parse_kap_financial_summary,
)
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, append_source


# Exact current KAP wording not present in the older generic mapping. In
# particular, bank balance sheets use these fixed labels. Do not treat
# "Yukumlulukler Toplami" as total liabilities because on the bank summary it
# equals liabilities + equity; BIAP leaves liabilities missing rather than
# mislabelling it.
_CURRENT_LABEL_MAP = {
    **_LABEL_MAP,
    "VARLIKLAR TOPLAMI": "total_assets",
    "OZKAYNAKLAR": "total_equity",
    "FAALIYET BRUT KARI": "gross_profit",
    "NET FAALIYET KARI (ZARARI)": "operating_income",
}

_FLIGHT_RE = re.compile(
    r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)',
    re.DOTALL,
)
_ROW_BOUNDARY_RE = re.compile(r'\n[0-9A-Za-z]+:\[')


def _flight_text(page_html: str) -> str:
    chunks: list[str] = []
    for match in _FLIGHT_RE.finditer(page_html):
        try:
            value = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, str):
            chunks.append(html_lib.unescape(value))
    return "\n".join(chunks)


def _annual_periods(text: str) -> tuple[str, Optional[str]]:
    periods = sorted({match.group(0) for match in re.finditer(r"20\d{2}/12", text)}, reverse=True)
    if not periods:
        raise GlobalProviderError("KAP Flight payload contains no completed annual YYYY/12 period")
    return periods[0], periods[1] if len(periods) > 1 else None


def _row_window(text: str, label_pos: int) -> str:
    end_match = _ROW_BOUNDARY_RE.search(text, label_pos)
    end = end_match.start() if end_match else min(len(text), label_pos + 14000)
    return text[label_pos:end]


def _period_value(row_text: str, period: str) -> Optional[str]:
    # KAP cell ids currently look like bilanco_2025/12_2, gelir_2025/12_2,
    # nakit_2025/12_2, etc. The prefix is intentionally unconstrained because
    # it is presentation metadata; period and explicit children value are what
    # matter. Limit the scan so a value cannot leak in from another row.
    pattern = re.compile(
        r'"[^"\n]*_' + re.escape(period) + r'_\d+".{0,900}?"children":"([^"]*)"',
        re.DOTALL,
    )
    match = pattern.search(row_text)
    return match.group(1) if match else None


def _label_rows(text: str):
    for match in re.finditer(r'"children":"([^"]+)"', text):
        raw = match.group(1)
        normalized = _ascii_upper(raw)
        yield normalized, match.start(), raw


def parse_kap_current_summary(page_html: str) -> dict:
    """Parse KAP semantic HTML first, then its current server-rendered Flight data."""
    try:
        return parse_kap_financial_summary(page_html)
    except GlobalProviderError:
        pass

    text = _flight_text(page_html)
    if not text:
        raise GlobalProviderError("KAP page contains neither usable tables nor server-rendered Flight financial data")
    annual_period, previous_period = _annual_periods(text)

    scale = 1.0
    currency = "TRY"
    report_scope = "unknown"
    for normalized, pos, _ in _label_rows(text):
        row = _row_window(text, pos)
        if normalized == "SUNUM PARA BIRIMI":
            raw = _period_value(row, annual_period)
            if raw:
                currency, scale = _currency_scale(raw)
                break

    for normalized, pos, _ in _label_rows(text):
        if normalized != "FINANSAL TABLO NITELIGI":
            continue
        raw = _period_value(_row_window(text, pos), annual_period)
        scope = _ascii_upper(raw or "")
        if "KONSOLIDE OLMAYAN" in scope:
            report_scope = "standalone"
        elif "KONSOLIDE" in scope:
            report_scope = "consolidated"
        if report_scope != "unknown":
            break

    values: dict[str, float] = {}
    previous_values: dict[str, float] = {}
    for normalized, pos, _ in _label_rows(text):
        field = _CURRENT_LABEL_MAP.get(normalized)
        if not field:
            continue
        row = _row_window(text, pos)
        raw = _period_value(row, annual_period)
        value = _number(raw) if raw is not None else None
        if value is not None and field not in values:
            values[field] = value * scale
        if previous_period:
            prev_raw = _period_value(row, previous_period)
            prev = _number(prev_raw) if prev_raw is not None else None
            if prev is not None and field not in previous_values:
                previous_values[field] = prev * scale

    if not values:
        raise GlobalProviderError("KAP Flight summary has no exact supported annual financial-statement labels")

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
        "reportScope": report_scope,
        "currency": currency,
        "transport": "nextjs-flight",
    }


class KAPCurrentFundamentalsProvider(KAPFundamentalsProvider):
    """Official KAP provider supporting semantic and current Flight-rendered pages."""

    provider_id = "kap-official-financial-summary"

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
        parsed = parse_kap_current_summary(self._get(financial_url))
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
                "kap_transport": parsed.get("transport", "semantic-html"),
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
