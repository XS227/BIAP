"""Exact issuer-published Italian annual-report fundamentals.

Only Fidia S.p.A. (FDA) is supported here. Values come from the issuer's
FY2025 consolidated annual report; absent fields remain None.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import io
import re
from typing import Optional

import httpx
from pypdf import PdfReader

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source

FIDIA_LEI = "815600D946B58C2B1D55"
FIDIA_TICKER = "FDA"
FIDIA_REPORT_URL = (
    "https://www.fidia.it/wp-content/uploads/investor_relations/borsa/bilanci/2025/"
    "Relazione_finanziaria_annuale_2025.pdf"
)
FIDIA_ONEINFO_PROTOCOL = "168475_oneinfo"
FIDIA_ONEINFO_STORED_AT = "2026-06-05T21:22:11+00:00"


def _thousands(raw: str) -> float:
    text = str(raw or "").strip().replace(" ", "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    value = float(text.replace(".", "").replace(",", "."))
    return (-value if negative else value) * 1000.0


def _match_thousands(text: str, pattern: str, *, required: bool = False) -> Optional[float]:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        if required:
            raise GlobalProviderError(f"Fidia annual report missing expected field pattern: {pattern[:80]}")
        return None
    return _thousands(match.group(1))


def parse_fidia_annual_text(raw_text: str) -> dict:
    text = " ".join(str(raw_text or "").replace("\u00a0", " ").split())
    upper = text.upper()
    if "FIDIA S.P.A." not in upper or FIDIA_LEI not in upper:
        raise GlobalProviderError("Fidia annual report identity/LEI verification failed")
    if "31 DICEMBRE 2025" not in upper and "31/12/2025" not in upper:
        raise GlobalProviderError("Fidia annual report is not FY2025")

    revenue = _match_thousands(text, r"ricavi consolidati pari a\s*([0-9.]+)\s*migliaia", required=True)
    ebitda = _match_thousands(text, r"EBITDA consolidato.{0,120}?pari a(?: Euro)?\s*([0-9.]+)\s*migliaia", required=True)
    net_income = _match_thousands(text, r"risultato netto consolidato.{0,100}?(?:utile di|pari a)\s*([0-9.]+)\s*migliaia", required=True)
    total_assets = _match_thousands(text, r"Totale Attivo\s+([0-9.]+)\s+[0-9.(]", required=True)
    total_equity = _match_thousands(text, r"Patrimonio netto del Gruppo e dei Terzi\s+([0-9.]+)", required=True)
    current_debt = _match_thousands(text, r"indebitamento finanziario corrente al 31 dicembre 2025.{0,100}?pari a\s*([0-9.]+)\s*migliaia", required=True)
    noncurrent_financing = _match_thousands(text, r"Finanziamenti a lungo termine,? al netto della quota corrente\s+([0-9.]+)", required=True)
    interest_expense = _match_thousands(text, r"interessi passivi\s*\(?([0-9.]+)\s*migliaia", required=True)
    capex = _match_thousands(text, r"Investimenti:\s*pari ad\s*([0-9.]+)\s*migliaia", required=True)
    cash = _match_thousands(text, r"(?:A\s+)?Disponibilità liquide\s+([0-9.]+)\s+[0-9.]+")
    operating_income = _match_thousands(text, r"Risultato operativo \(EBIT\)\s+\(?([0-9.]+)\)?\s+-?[0-9.,]+%")
    if operating_income is not None and re.search(r"Risultato operativo \(EBIT\)\s+\([0-9.]+\)", text, flags=re.IGNORECASE):
        operating_income = -abs(operating_income)

    total_debt = current_debt + noncurrent_financing
    total_liabilities = total_assets - total_equity
    return {
        "revenue": revenue,
        "ebitda": ebitda,
        "net_income": net_income,
        "total_assets": total_assets,
        "total_equity": total_equity,
        "total_liabilities": total_liabilities,
        "total_debt": total_debt,
        "interest_expense": interest_expense,
        "cash_and_equivalents": cash,
        "operating_income": operating_income,
        "capex": capex,
    }


class ItalyIssuerFundamentalsProvider(FundamentalsProvider):
    provider_id = "it-official-issuer-financials-v1"

    def __init__(self, *, timeout: float = 45.0) -> None:
        self.timeout = max(10.0, float(timeout))

    @staticmethod
    def _supported(company: GlobalCompany) -> bool:
        return company.country.upper() == "IT" and company.ticker.upper() == FIDIA_TICKER and (
            not company.lei or company.lei.upper() == FIDIA_LEI
        )

    def _text(self) -> str:
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": "BIAP-Global/1.0 issuer annual-report evidence"},
            ) as client:
                response = client.get(FIDIA_REPORT_URL)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GlobalProviderError(f"Fidia official annual-report download failed: {type(exc).__name__}") from exc
        try:
            reader = PdfReader(io.BytesIO(response.content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:40])
        except Exception as exc:
            raise GlobalProviderError(f"Fidia annual-report PDF parse failed: {type(exc).__name__}") from exc
        if not text.strip():
            raise GlobalProviderError("Fidia annual report PDF yielded no text")
        return text

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if not self._supported(company):
            raise GlobalProviderError("issuer-specific Italian provider does not support this company")
        values = parse_fidia_annual_text(self._text())
        capex = values.pop("capex")
        fetched = datetime.now(timezone.utc).isoformat()
        enriched = replace(
            company,
            name="Fidia S.p.A.",
            lei=FIDIA_LEI,
            reporting_currency="EUR",
            **values,
            filing_period_end="2025-12-31",
            filing_observed_at=FIDIA_ONEINFO_STORED_AT,
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "issuer_report_url": FIDIA_REPORT_URL,
                "issuer_report_lei_verified": True,
                "issuer_report_capex": capex,
                "issuer_total_liabilities_method": "total_assets_minus_total_equity_same_consolidated_scope",
                "issuer_total_debt_method": "current_financial_debt_plus_noncurrent_financing",
                "oneinfo_protocol": FIDIA_ONEINFO_PROTOCOL,
                "oneinfo_stored_at": FIDIA_ONEINFO_STORED_AT,
                "issuer_report_retrieved_at": fetched,
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_issuer_financial_statement",
            source_id="FIDIA-FY2025",
            source_url=FIDIA_REPORT_URL,
            observed_at=FIDIA_ONEINFO_STORED_AT,
            period_end="2025-12-31",
            quality=0.96,
            notes=(
                "Fidia S.p.A. issuer-published FY2025 consolidated annual financial report; "
                f"document LEI {FIDIA_LEI} verified. 1INFO storage protocol {FIDIA_ONEINFO_PROTOCOL}. "
                "Audit opinion is not inferred from auditor identity."
            ),
            provenance_status="independently_verified",
            audit_status="unknown",
        ))
