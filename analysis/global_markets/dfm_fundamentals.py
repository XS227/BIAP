"""Official DFM annual-statement fundamentals.

Dubai Financial Market's Efsah API publishes issuer financial-report metadata,
and the DFM document feed serves the original filed PDF. BIAP selects the
latest completed yearly report, downloads the English statement, and extracts
only conservative headline values from the primary statements. Missing or
ambiguous values stay missing rather than being guessed.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import io
import json
import re
from typing import Optional

import requests
from pypdf import PdfReader

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source


_LIST_URL = "https://api2.dfm.ae/efsah/v1/prototype_efsah"
_RESOURCE_BASE = "https://feeds.dfm.ae/documents"
_PAGE_URL = "https://www.dfm.ae/the-exchange/market-information"
_PROVIDER_ID = "official-dfm-efsah-annual-statement"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_NUMBER = r"\(?-?[\d][\d,]*(?:\.\d+)?\)?"


def _json_bom_safe(content: bytes) -> object:
    try:
        return json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GlobalProviderError("DFM Efsah returned invalid JSON") from exc


def select_latest_dfm_annual(payload: object, symbol: str) -> tuple[dict, dict]:
    if not isinstance(payload, dict):
        raise GlobalProviderError("DFM Efsah response is not an object")
    root = payload.get("root")
    rows = root if isinstance(root, list) else ([root] if isinstance(root, dict) else [])
    wanted = symbol.strip().upper()
    annual: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("issuer_symbol") or "").strip().upper() != wanted:
            continue
        if str(row.get("report_interval") or "").strip().casefold() != "yearly":
            continue
        resources = row.get("resources")
        if not isinstance(resources, list):
            continue
        pdfs = [
            resource for resource in resources
            if isinstance(resource, dict)
            and str(resource.get("type") or "").strip().casefold() == "financial_reports"
            and str(resource.get("r_path") or "").strip().lower().endswith(".pdf")
        ]
        if not pdfs:
            continue
        english = [
            resource for resource in pdfs
            if str(resource.get("language") or "").strip().casefold() in {"en", "english"}
        ]
        annual.append({**row, "_selected_resource": (english or pdfs)[0]})
    if not annual:
        raise GlobalProviderError(f"DFM Efsah has no yearly financial statement for {wanted}")

    def sort_key(row: dict) -> tuple[int, str]:
        years = re.findall(r"\b(20\d{2})\b", str(row.get("headline") or ""))
        year = int(years[-1]) if years else 0
        return year, str(row.get("publication_date") or "")

    latest = max(annual, key=sort_key)
    return latest, latest["_selected_resource"]


def _to_number(text: str) -> Optional[float]:
    value = str(text or "").strip().replace(",", "")
    if not value or value in {"-", "—"}:
        return None
    negative = value.startswith("(") and value.endswith(")")
    value = value.strip("()")
    try:
        number = float(value)
    except ValueError:
        return None
    return -number if negative else number


def _first_value(text: str, patterns: tuple[str, ...]) -> Optional[float]:
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.M)
        if match:
            value = _to_number(match.group(1))
            if value is not None:
                return value
    return None


def _statement_scale(text: str) -> float:
    if re.search(r"AED\s*[’']?\s*000\b", text, re.I):
        return 1000.0
    if re.search(r"AED\s+million\b", text, re.I):
        return 1_000_000.0
    return 1.0


def parse_dfm_statement_text(text: str) -> dict[str, Optional[float]]:
    if not text or len(text) < 200:
        raise GlobalProviderError("DFM annual PDF has insufficient extractable text")
    scale = _statement_scale(text)

    revenue = _first_value(text, (
        rf"^\s*Revenue(?:\s+\d+)?\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
    ))
    net_income = _first_value(text, (
        rf"^\s*Profit after tax for (?:the )?(?:period|year)\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
        rf"^\s*Profit for the year after tax\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
        rf"^\s*Profit for the year after[\s\S]{0,120}?tax\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
        rf"^\s*Profit for the year\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
    ))
    total_assets = _first_value(text, (
        rf"^\s*Total assets\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
    ))
    total_liabilities = _first_value(text, (
        rf"^\s*Total liabilities\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
    ))
    total_equity = _first_value(text, (
        rf"^\s*Total equity\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
        # Some DFM PDFs have a damaged text layer on the statement of financial
        # position. The statement of changes in equity is often clean; its final
        # column is Total equity, so the last value on the year-end row is a
        # conservative fallback.
        rf"^\s*At 31 December 20\d{{2}}.*\s({_NUMBER})\s*$",
    ))
    current_assets = _first_value(text, (
        rf"^\s*Total current assets\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
    ))
    current_liabilities = _first_value(text, (
        rf"^\s*Total current liabilities\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
    ))
    cash = _first_value(text, (
        rf"^\s*Cash and cash equivalents(?:\s+\d+)?\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
        rf"^\s*Cash and cash equivalents at the end of the year(?:\s+\d+)?\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
    ))
    operating_cash_flow = _first_value(text, (
        rf"^\s*Net cash generated from operating activities\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
        rf"^\s*Net cash from operating activities\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
    ))
    gross_profit = _first_value(text, (
        rf"^\s*Gross profit\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
    ))
    operating_income = _first_value(text, (
        rf"^\s*Operating profit\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
    ))
    eps = _first_value(text, (
        rf"^\s*Basic and diluted earnings per share \(AED\)(?:\s+\d+)?\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
        rf"^\s*Basic earnings per share \(AED\)(?:\s+\d+)?\s+({_NUMBER})(?:\s+{_NUMBER})?\s*$",
    ))

    values: dict[str, Optional[float]] = {
        "revenue": revenue,
        "net_income": net_income,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "current_assets": current_assets,
        "current_liabilities": current_liabilities,
        "cash_and_equivalents": cash,
        "operating_cash_flow": operating_cash_flow,
        "gross_profit": gross_profit,
        "operating_income": operating_income,
        "eps": eps,
        "scale": scale,
    }
    for key in (
        "revenue", "net_income", "total_assets", "total_liabilities", "total_equity",
        "current_assets", "current_liabilities", "cash_and_equivalents",
        "operating_cash_flow", "gross_profit", "operating_income",
    ):
        value = values[key]
        if value is not None:
            values[key] = value * scale

    if (
        values["total_liabilities"] is None
        and values["total_assets"] is not None
        and values["total_equity"] is not None
        and "regulatory deferral" not in text.casefold()
    ):
        # For ordinary balance sheets assets = liabilities + equity. Do not use
        # this identity when a regulator-specific deferral balance is presented
        # outside liabilities/equity (for example DEWA), because doing so would
        # silently misclassify that balance as a liability.
        derived = float(values["total_assets"]) - float(values["total_equity"])
        if derived >= 0:
            values["total_liabilities"] = derived

    return values


class DFMEfsahAnnualFundamentalsProvider(FundamentalsProvider):
    provider_id = _PROVIDER_ID

    def __init__(self, *, timeout: float = 55.0, max_pages: int = 25) -> None:
        self.timeout = max(10.0, float(timeout))
        self.max_pages = max(10, min(40, int(max_pages)))

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if (company.country.upper(), company.exchange.upper()) != ("AE", "DFM"):
            raise GlobalProviderError(
                f"DFM Efsah fundamentals are not configured for {company.country}/{company.exchange}"
            )
        symbol = company.ticker.strip().upper()
        try:
            listing = requests.get(
                _LIST_URL,
                params={
                    "types": "financial_reports",
                    "announcement_type": "Disclosure",
                    "symbol": symbol,
                    "take": 24,
                    "lang": "en",
                    "cms_resources": "true",
                },
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json", "Referer": _PAGE_URL},
                timeout=self.timeout,
            )
            listing.raise_for_status()
            annual, resource = select_latest_dfm_annual(_json_bom_safe(listing.content), symbol)
            path = str(resource.get("r_path") or "").strip()
            pdf_url = _RESOURCE_BASE + "/" + path.lstrip("/")
            pdf = requests.get(
                pdf_url,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/pdf", "Referer": _PAGE_URL},
                timeout=self.timeout,
            )
            pdf.raise_for_status()
            if not pdf.content.startswith(b"%PDF"):
                raise GlobalProviderError("DFM Efsah annual resource is not a PDF")
            reader = PdfReader(io.BytesIO(pdf.content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[: self.max_pages])
        except (requests.RequestException, ValueError, OSError) as exc:
            raise GlobalProviderError(
                f"DFM Efsah annual statement request failed: {type(exc).__name__}"
            ) from exc

        metrics = parse_dfm_statement_text(text)
        years = re.findall(r"\b(20\d{2})\b", str(annual.get("headline") or ""))
        if not years:
            raise GlobalProviderError("DFM annual statement year could not be verified")
        year = years[-1]

        critical = (
            metrics.get("net_income"),
            metrics.get("total_assets"),
            metrics.get("total_equity"),
            metrics.get("operating_cash_flow"),
        )
        if sum(value is not None for value in critical) < 3:
            raise GlobalProviderError(
                "DFM annual statement did not yield enough verified headline fields"
            )

        revenue = metrics.get("revenue")
        net_income = metrics.get("net_income")
        net_margin = (
            float(net_income) / float(revenue) * 100.0
            if net_income is not None and revenue not in (None, 0)
            else None
        )
        observed = datetime.now(timezone.utc).isoformat()
        headline = str(annual.get("headline") or "")
        publication = str(annual.get("publication_date") or "").strip()
        scope = "consolidated" if "consolidated" in text[:16000].casefold() else "annual financial statements"
        enriched = replace(
            company,
            reporting_currency="AED",
            revenue=revenue,
            gross_profit=metrics.get("gross_profit"),
            operating_income=metrics.get("operating_income"),
            net_income=net_income,
            net_margin_pct=net_margin,
            total_assets=metrics.get("total_assets"),
            total_liabilities=metrics.get("total_liabilities"),
            total_equity=metrics.get("total_equity"),
            current_assets=metrics.get("current_assets"),
            current_liabilities=metrics.get("current_liabilities"),
            cash_and_equivalents=metrics.get("cash_and_equivalents"),
            operating_cash_flow=metrics.get("operating_cash_flow"),
            eps=metrics.get("eps"),
            filing_period_end=f"{year}-12-31",
            filing_observed_at=observed,
            report_scope=scope,
            raw_provider_fields={
                **company.raw_provider_fields,
                "dfm_efsah_disclosure_id": annual.get("id"),
                "dfm_efsah_resource_id": resource.get("id"),
                "dfm_efsah_publication_date": publication,
                "dfm_efsah_headline": headline,
                "dfm_efsah_pdf_url": pdf_url,
                "dfm_statement_scale": metrics.get("scale"),
            },
        )
        return append_source(
            enriched,
            SourceEvidence(
                provider=self.provider_id,
                source_type="official_exchange_financial_statement",
                source_id=f"DFM:{symbol}:{annual.get('id')}",
                source_url=pdf_url,
                observed_at=observed,
                period_end=f"{year}-12-31",
                quality=0.99,
                notes=(
                    "DFM Efsah issuer-filed yearly financial statement PDF; "
                    "headline values extracted conservatively from primary statements."
                ),
            ),
        )
