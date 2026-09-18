"""Whitelisted official issuer fundamentals for German Xetra probes.

Germany's Company Register publishes the legally required ESEF rendering, but
its public search flow is interactive and is not a stable unattended API. BIAP
therefore keeps the regulator/ESEF path as the primary generic route and, for a
small explicitly verified issuer allow-list, can consume the issuer's own
published annual financial-results pages as an additional official source.

This adapter is intentionally narrow:
* only exact DE/Xetra issuer identities are accepted;
* URLs are hard-coded official issuer domains, never user supplied;
* the expected reporting period must be present in the source text;
* parsing failure blocks the source instead of guessing;
* source provenance states that this is issuer-published evidence, not a
  regulator filing.

The allow-list can be expanded only with a parser/test for each issuer.
"""
from __future__ import annotations

from dataclasses import replace
from html import unescape
import re

import httpx

from .gleif import _legal_core
from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source


_SIEMENS_URL = (
    "https://press.siemens.com/global/en/pressrelease/"
    "earnings-release-and-financial-results-q4-fy-2025"
)
_ALLIANZ_URL = (
    "https://www.allianz.com/en/investor_relations/results-reports/"
    "financial-statements.html"
)


def _plain_text(value: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", value or "")
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text).replace("\xa0", " ")
    return " ".join(text.split())


def _million_number(value: str) -> float:
    return float(value.replace(",", "").strip()) * 1_000_000.0


def _billion_number(value: str) -> float:
    return float(value.replace(",", "").strip()) * 1_000_000_000.0


def _required_match(pattern: str, text: str, *, label: str) -> re.Match[str]:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if match is None:
        raise GlobalProviderError(f"German issuer source missing verified {label}")
    return match


def _row_pair(text: str, label: str) -> tuple[float, float]:
    # Allianz's official statement page renders table cells in row order. Keep
    # the match deliberately local so a later similarly named row cannot be
    # substituted silently.
    pattern = (
        rf"\b{re.escape(label)}\b\s+"
        r"([+-]?[0-9][0-9,]*(?:\.[0-9]+)?)\s+"
        r"([+-]?[0-9][0-9,]*(?:\.[0-9]+)?)"
    )
    match = _required_match(pattern, text, label=label)
    return _million_number(match.group(1)), _million_number(match.group(2))


class GermanIssuerFundamentalsProvider(FundamentalsProvider):
    """Exact-identity official issuer annual fundamentals for DE/Xetra."""

    provider_id = "de-official-issuer-financials"

    def __init__(self, *, timeout: float = 15.0) -> None:
        self.timeout = max(3.0, float(timeout))

    def _get_text(self, url: str) -> str:
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": "BIAP-Global/1.0 official-issuer-financials",
                },
            ) as client:
                response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GlobalProviderError(
                f"German official issuer request failed: {type(exc).__name__}"
            ) from exc
        text = _plain_text(response.text)
        if len(text) < 200:
            raise GlobalProviderError("German official issuer response is unexpectedly short")
        return text

    @staticmethod
    def _identity(company: GlobalCompany) -> str:
        if company.country.strip().upper() != "DE":
            raise GlobalProviderError("German issuer adapter only supports DE")
        ticker = company.ticker.strip().upper()
        expected = {"SIE": "SIEMENS", "ALV": "ALLIANZ"}.get(ticker)
        if expected is None:
            raise GlobalProviderError(f"no verified German issuer parser for {ticker}")
        if _legal_core(company.name) != expected:
            raise GlobalProviderError(
                f"German issuer identity mismatch for {ticker}: {company.name!r}"
            )
        return ticker

    def _siemens(self, company: GlobalCompany) -> GlobalCompany:
        text = self._get_text(_SIEMENS_URL)
        if "fiscal 2025" not in text.lower() or "Siemens AG" not in text:
            raise GlobalProviderError("Siemens FY2025 issuer source identity/period marker missing")

        revenue = _billion_number(_required_match(
            r"full fiscal year.*?revenue increased\s+4%\s+to\s+€?\s*([0-9]+(?:\.[0-9]+)?)\s+billion",
            text,
            label="Siemens FY2025 revenue",
        ).group(1))
        net_income = _billion_number(_required_match(
            r"fiscal 2025.*?net income climbed\s+16%\s+to.*?€?\s*([0-9]+(?:\.[0-9]+)?)\s+billion",
            text,
            label="Siemens FY2025 net income",
        ).group(1))
        free_cash_flow = _billion_number(_required_match(
            r"free cash flow.*?for fiscal 2025.*?€?\s*([0-9]+(?:\.[0-9]+)?)\s+billion",
            text,
            label="Siemens FY2025 free cash flow",
        ).group(1))
        eps = float(_required_match(
            r"basic EPS increased to\s+€?\s*([0-9]+(?:\.[0-9]+)?)",
            text,
            label="Siemens FY2025 EPS",
        ).group(1))

        enriched = replace(
            company,
            reporting_currency="EUR",
            revenue=revenue,
            revenue_yoy_pct=4.0,
            net_income=net_income,
            net_margin_pct=(net_income / revenue) * 100.0 if revenue else None,
            free_cash_flow=free_cash_flow,
            eps=eps,
            filing_period_end="2025-09-30",
            filing_observed_at="2025-11-13T00:00:00+00:00",
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "de_issuer_source": "siemens_fy2025_results",
                "de_issuer_evidence_kind": "issuer_published_annual_results",
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_issuer_financial_statement_summary",
            source_id="siemens-fy2025-results",
            source_url=_SIEMENS_URL,
            observed_at="2025-11-13T00:00:00+00:00",
            period_end="2025-09-30",
            quality=0.93,
            notes=(
                "Siemens issuer-published FY2025 consolidated financial results; "
                "official issuer evidence, not a regulator filing"
            ),
        ))

    def _allianz(self, company: GlobalCompany) -> GlobalCompany:
        text = self._get_text(_ALLIANZ_URL)
        lower = text.lower()
        if (
            "consolidated balance sheet as of december 31, 2025" not in lower
            or "consolidated income statements 2025" not in lower
        ):
            raise GlobalProviderError("Allianz FY2025 issuer source period marker missing")

        revenue, revenue_prev = _row_pair(text, "Insurance revenue")
        net_income, net_income_prev = _row_pair(text, "Net income")
        total_assets, _ = _row_pair(text, "Total assets")
        total_liabilities, _ = _row_pair(text, "Total liabilities")
        total_equity, _ = _row_pair(text, "Total equity")
        cash, _ = _row_pair(text, "Cash and cash equivalents")

        eps_match = _required_match(
            r"Basic earnings per share\s*\(EUR\)\s+"
            r"([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)",
            text,
            label="Allianz basic EPS",
        )
        eps = float(eps_match.group(1))
        revenue_yoy = ((revenue / revenue_prev) - 1.0) * 100.0 if revenue_prev else None
        margin = (net_income / revenue) * 100.0 if revenue else None
        margin_prev = (net_income_prev / revenue_prev) * 100.0 if revenue_prev else None

        enriched = replace(
            company,
            reporting_currency="EUR",
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=revenue_yoy,
            net_income=net_income,
            net_margin_pct=margin,
            net_margin_prev_pct=margin_prev,
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            total_equity=total_equity,
            cash_and_equivalents=cash,
            eps=eps,
            filing_period_end="2025-12-31",
            filing_observed_at="2026-03-13T00:00:00+00:00",
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "de_issuer_source": "allianz_fy2025_financial_statements",
                "de_issuer_evidence_kind": "issuer_published_financial_statements",
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_issuer_financial_statement",
            source_id="allianz-fy2025-financial-statements",
            source_url=_ALLIANZ_URL,
            observed_at="2026-03-13T00:00:00+00:00",
            period_end="2025-12-31",
            quality=0.96,
            notes=(
                "Allianz issuer-published FY2025 consolidated balance sheet and "
                "income statement; official issuer evidence, not a regulator filing"
            ),
        ))

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        ticker = self._identity(company)
        if ticker == "SIE":
            return self._siemens(company)
        if ticker == "ALV":
            return self._allianz(company)
        raise GlobalProviderError(f"no verified German issuer parser for {ticker}")
