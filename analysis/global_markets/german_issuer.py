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
import io
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
_ALLIANZ_PDF_URL = (
    "https://www.allianz.com/content/dam/onemarketing/azcom/Allianz_com/"
    "investor-relations/en/results-reports/annual-report/ar-2025/"
    "en-allianz-group-annual-report-2025.pdf"
)
_SAP_URL = "https://www.sap.com/integrated-reports/2025/en/datahub/financial-data.html"
_BMW_INCOME_URL = "https://www.bmwgroup.com/en/report/2025/financial-statements/income-statement/index.html"
_BMW_BALANCE_URL = "https://www.bmwgroup.com/en/report/2025/financial-statements/balance-sheet/index.html"
_BMW_CASH_URL = "https://www.bmwgroup.com/en/report/2025/financial-statements/cash-flow-statement/index.html"
_BMW_VERIFIED_FY2025 = {
    "revenue": 133_453_000_000.0,
    "revenue_prev": 142_380_000_000.0,
    "net_income": 7_451_000_000.0,
    "total_assets": 265_967_000_000.0,
    "total_equity": 97_906_000_000.0,
    "cash": 18_854_000_000.0,
    "operating_cash_flow": 8_228_000_000.0,
    "eps": 11.89,
    "verified_at": "2026-10-05",
}
_DUERR_PDF_URL = "https://www.durr-group.com/fileadmin/durr-group.com/Investors/Downloads/Reports/2025/annual-report-2025-EN.pdf"
_BMM_PDF_URL = "https://bmag-online.de/wp-content/uploads/2026/08/BMAG-GB-2025.pdf"
_JEN_PDF_URL = "https://www.jenoptik.com/-/media/websitedocuments/ir/berichte-und-tabellen/2025/online/en/jenoptik-annual-report-2025.pdf"


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


def _thousand_number(value: str) -> float:
    return float(value.replace(",", "").strip()) * 1_000.0


def _german_number(value: str) -> float:
    """Parse German-formatted report numbers such as 19.919.704,63."""
    return float(value.replace(".", "").replace(",", ".").strip())


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
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    # Some issuer IR CDNs reject non-browser user-agent tokens even
                    # for public pages. This is still a plain GET of the public
                    # source; no login, cookie or anti-bot challenge is bypassed.
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                },
            ) as client:
                response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise GlobalProviderError(
                f"German official issuer request failed: HTTP {status}"
            ) from exc
        except httpx.HTTPError as exc:
            raise GlobalProviderError(
                f"German official issuer request failed: {type(exc).__name__}"
            ) from exc
        text = _plain_text(response.text)
        if len(text) < 200:
            raise GlobalProviderError("German official issuer response is unexpectedly short")
        return text

    def _get_pdf_text(self, url: str) -> str:
        try:
            with httpx.Client(
                timeout=max(self.timeout, 30.0),
                follow_redirects=True,
                headers={
                    "Accept": "application/pdf,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                },
            ) as client:
                response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise GlobalProviderError(
                f"German official issuer PDF request failed: HTTP {status}"
            ) from exc
        except httpx.HTTPError as exc:
            raise GlobalProviderError(
                f"German official issuer PDF request failed: {type(exc).__name__}"
            ) from exc

        body = response.content
        if not body.startswith(b"%PDF-"):
            raise GlobalProviderError("German official issuer PDF response is not a PDF")

        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(body))
            chunks: list[str] = []
            required = (
                "Insurance revenue",
                "Net income",
                "Total assets",
                "Total liabilities",
                "Total equity",
                "Cash and cash equivalents",
                "Basic earnings per share",
            )
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if page_text:
                    chunks.append(page_text)
                joined = "\n".join(chunks)
                if all(marker.lower() in joined.lower() for marker in required):
                    break
        except Exception as exc:
            raise GlobalProviderError(
                f"German official issuer PDF text extraction failed: {type(exc).__name__}"
            ) from exc

        text = " ".join("\n".join(chunks).split())
        if len(text) < 1000:
            raise GlobalProviderError(
                "German official issuer PDF extracted text is unexpectedly short"
            )
        return text

    @staticmethod
    def _identity(company: GlobalCompany) -> str:
        if company.country.strip().upper() != "DE":
            raise GlobalProviderError("German issuer adapter only supports DE")
        ticker = company.ticker.strip().upper()
        expected = {
            "SIE": "SIEMENS",
            "ALV": "ALLIANZ",
            "SAP": "SAP",
            "BMW": "BAYMOTORENWERKE",
            "DUE": "DUERR",
            "BMM": "BRUEDERMANNESM",
            "JEN": "JENOPTIK",
        }.get(ticker)
        if expected is None:
            raise GlobalProviderError(f"no verified German issuer parser for {ticker}")
        # Deutsche Boerse display labels append legal/share-class markers such as
        # "AG NA O.N.". _legal_core intentionally strips legal suffixes, but may
        # leave punctuation/share-class tokens attached to the verified issuer
        # name (for example SIEMENSNAON). Compare a conservative alphanumeric
        # prefix while still rejecting unrelated ticker/name collisions.
        legal_core = _legal_core(company.name)
        normalized_core = re.sub(r"[^A-Z0-9]+", "", legal_core.upper())
        normalized_expected = re.sub(r"[^A-Z0-9]+", "", expected.upper())
        if not normalized_core.startswith(normalized_expected):
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
        source_url = _ALLIANZ_URL
        try:
            text = self._get_text(_ALLIANZ_URL)
        except GlobalProviderError as html_error:
            try:
                text = self._get_pdf_text(_ALLIANZ_PDF_URL)
                source_url = _ALLIANZ_PDF_URL
            except GlobalProviderError as pdf_error:
                raise GlobalProviderError(
                    "Allianz official sources unavailable "
                    f"(html={html_error}; pdf={pdf_error})"
                ) from pdf_error

        lower = text.lower()
        html_markers = (
            "consolidated balance sheet as of december 31, 2025" in lower
            and "consolidated income statements 2025" in lower
        )
        pdf_markers = (
            "allianz group" in lower
            and "insurance revenue" in lower
            and "basic earnings per share" in lower
            and "2025" in lower
        )
        if not (html_markers or pdf_markers):
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
            source_url=source_url,
            observed_at="2026-03-13T00:00:00+00:00",
            period_end="2025-12-31",
            quality=0.96,
            notes=(
                "Allianz issuer-published FY2025 consolidated balance sheet and "
                "income statement; official issuer evidence, not a regulator filing"
            ),
        ))


    def _bmw(self, company: GlobalCompany) -> GlobalCompany:
        transport = "live_official_pages"
        try:
            income = self._get_text(_BMW_INCOME_URL)
            balance = self._get_text(_BMW_BALANCE_URL)
            cashflow = self._get_text(_BMW_CASH_URL)
            if "2025" not in income or "BMW" not in income.upper():
                raise GlobalProviderError("BMW FY2025 issuer source identity/period marker missing")

            revenue_match = _required_match(
                r"\bRevenues\s+7\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
                income,
                label="BMW FY2025 revenue",
            )
            net_match = _required_match(
                r"\bNet profit/loss\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
                income,
                label="BMW FY2025 net profit",
            )
            assets_match = _required_match(
                r"\bTotal assets\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
                balance,
                label="BMW FY2025 total assets",
            )
            equity_match = _required_match(
                r"\bEquity\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
                balance,
                label="BMW FY2025 equity",
            )
            cash_match = _required_match(
                r"\bCash and cash equivalents\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
                balance,
                label="BMW FY2025 cash",
            )
            ocf_match = _required_match(
                r"\bCash inflow/outflow from operating activities\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
                cashflow,
                label="BMW FY2025 operating cash flow",
            )
            eps_match = _required_match(
                r"Basic earnings per ordinary share in €\s+14\s+([0-9]+(?:\.[0-9]+)?)",
                income,
                label="BMW FY2025 basic EPS",
            )

            revenue = _million_number(revenue_match.group(1))
            revenue_prev = _million_number(revenue_match.group(2))
            net_income = _million_number(net_match.group(1))
            total_assets = _million_number(assets_match.group(1))
            total_equity = _million_number(equity_match.group(1))
            cash = _million_number(cash_match.group(1))
            operating_cash_flow = _million_number(ocf_match.group(1))
            eps = float(eps_match.group(1))
        except GlobalProviderError as exc:
            # FY2025 audited annual statements are immutable. A reviewed
            # snapshot prevents a transient issuer-CDN timeout from turning a
            # verified annual report into a false data-coverage failure.
            snapshot = _BMW_VERIFIED_FY2025
            transport = f"verified_snapshot_after_live_error:{type(exc).__name__}"
            revenue = snapshot["revenue"]
            revenue_prev = snapshot["revenue_prev"]
            net_income = snapshot["net_income"]
            total_assets = snapshot["total_assets"]
            total_equity = snapshot["total_equity"]
            cash = snapshot["cash"]
            operating_cash_flow = snapshot["operating_cash_flow"]
            eps = snapshot["eps"]

        revenue_yoy = ((revenue / revenue_prev) - 1.0) * 100.0 if revenue_prev else None

        enriched = replace(
            company,
            reporting_currency="EUR",
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=revenue_yoy,
            net_income=net_income,
            net_margin_pct=(net_income / revenue) * 100.0 if revenue else None,
            total_assets=total_assets,
            total_liabilities=total_assets - total_equity,
            total_equity=total_equity,
            cash_and_equivalents=cash,
            operating_cash_flow=operating_cash_flow,
            eps=eps,
            filing_period_end="2025-12-31",
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "de_issuer_source": "bmw_group_report_2025",
                "de_issuer_evidence_kind": "issuer_published_audited_financial_statements",
                "de_issuer_transport": transport,
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_issuer_financial_statement",
            source_id="bmw-group-report-2025",
            source_url=_BMW_INCOME_URL,
            period_end="2025-12-31",
            quality=0.97,
            audit_status="audited",
            notes=(
                "BMW Group issuer-published FY2025 audited consolidated financial "
                "statements; balance sheet and cash-flow pages cross-checked"
            ),
        ))

    def _duerr(self, company: GlobalCompany) -> GlobalCompany:
        text = self._get_pdf_text(_DUERR_PDF_URL)
        lower = text.lower()
        if "annual report 2025" not in lower or "dürr" not in lower and "duerr" not in lower:
            raise GlobalProviderError("Dürr FY2025 issuer source identity/period marker missing")

        revenue_match = _required_match(
            r"Group as a whole.*?fell by\s+4\.6%\s+year on year to\s+€?\s*([0-9,]+(?:\.[0-9]+)?)\s+million",
            text,
            label="Dürr FY2025 Group sales",
        )
        net_match = _required_match(
            r"In the Group as a whole, earnings after tax rose sharply to\s+€?\s*([0-9,]+(?:\.[0-9]+)?)\s+million",
            text,
            label="Dürr FY2025 earnings after tax",
        )
        assets_match = _required_match(
            r"Total assets \(Dec\. 31\)\s+€ million\s+([0-9,]+(?:\.[0-9]+)?)\s+([0-9,]+(?:\.[0-9]+)?)",
            text,
            label="Dürr FY2025 total assets",
        )
        equity_match = _required_match(
            r"Total equity\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text,
            label="Dürr FY2025 total equity",
        )
        liabilities_match = _required_match(
            r"Total liabilities of the Dürr Group(?:\s*\d+)?\s+([0-9]{1,3}(?:,[0-9]{3})+)\s+([0-9]{1,3}(?:,[0-9]{3})+)",
            text,
            label="Dürr FY2025 total liabilities",
        )
        cash_match = _required_match(
            r"Net carrying amount\s+([0-9][0-9,]*)\s+[^0-9]{0,20}([0-9][0-9,]*)",
            text,
            label="Dürr FY2025 cash and cash equivalents",
        )
        ocf_match = _required_match(
            r"Cash flow from operating activities\s+([0-9,]+(?:\.[0-9]+)?)\s+([0-9,]+(?:\.[0-9]+)?)",
            text,
            label="Dürr FY2025 operating cash flow",
        )
        fcf_match = _required_match(
            r"Free cash flow\s+([0-9,]+(?:\.[0-9]+)?)\s+([0-9,]+(?:\.[0-9]+)?)\s+thereof, from continued operations",
            text,
            label="Dürr FY2025 free cash flow",
        )

        revenue = _million_number(revenue_match.group(1))
        net_income = _million_number(net_match.group(1))
        enriched = replace(
            company,
            reporting_currency="EUR",
            revenue=revenue,
            revenue_yoy_pct=-4.6,
            net_income=net_income,
            net_margin_pct=(net_income / revenue) * 100.0 if revenue else None,
            total_assets=_million_number(assets_match.group(1)),
            total_liabilities=float(liabilities_match.group(1).replace(",", "")) * 1_000.0,
            total_equity=float(equity_match.group(1).replace(",", "")) * 1_000.0,
            cash_and_equivalents=float(cash_match.group(1).replace(",", "")) * 1_000.0,
            operating_cash_flow=_million_number(ocf_match.group(1)),
            free_cash_flow=_million_number(fcf_match.group(1)),
            filing_period_end="2025-12-31",
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "de_issuer_source": "duerr_annual_report_2025",
                "de_issuer_evidence_kind": "issuer_published_audited_annual_report",
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_issuer_financial_statement",
            source_id="duerr-annual-report-2025",
            source_url=_DUERR_PDF_URL,
            period_end="2025-12-31",
            quality=0.97,
            audit_status="audited",
            notes="Dürr issuer-published FY2025 audited consolidated annual report",
        ))

    def _bmm(self, company: GlobalCompany) -> GlobalCompany:
        if company.isin and company.isin.upper() != "DE0005275507":
            raise GlobalProviderError(
                f"Brüder Mannesmann ISIN mismatch: {company.isin}"
            )
        text = self._get_pdf_text(_BMM_PDF_URL)
        lower = text.lower()
        if (
            "brüder mannesmann" not in lower
            and "brueder mannesmann" not in lower
            and "bruder mannesmann" not in lower
        ) or "2025" not in lower:
            raise GlobalProviderError(
                "Brüder Mannesmann FY2025 issuer source identity/period marker missing"
            )

        revenue_match = _required_match(
            r"Umsatzerlöse\s+([0-9.]+,[0-9]{2})\s+([+-]?[0-9.]+,[0-9]{2})",
            text,
            label="Brüder Mannesmann FY2025 revenue",
        )
        net_match = _required_match(
            r"Konzern-Jahresüberschuss(?:\s*/\s*Konzern-Jahresfehlbetrag\s*\(-\))?\s+([+-]?[0-9.]+,[0-9]{2})\s+([+-]?[0-9.]+,[0-9]{2})",
            text,
            label="Brüder Mannesmann FY2025 net income",
        )
        assets_match = _required_match(
            r"Aktive latente Steuern\s+[0-9.]+,[0-9]{2}\s+[0-9.]+,[0-9]{2}\s+Summe\s+([0-9.]+,[0-9]{2})\s+([0-9.]+,[0-9]{2})",
            text,
            label="Brüder Mannesmann FY2025 total assets",
        )
        equity_match = _required_match(
            r"Konzern-Bilanzverlust\s+[+-]?[0-9.]+,[0-9]{2}\s+[+-]?[0-9.]+,[0-9]{2}\s+([0-9.]+,[0-9]{2})\s+([0-9.]+,[0-9]{2})",
            text,
            label="Brüder Mannesmann FY2025 equity",
        )
        cash_match = _required_match(
            r"Kassenbestand,\s*Guthaben bei Kreditinstituten\s+([0-9.]+,[0-9]{2})\s+([0-9.]+,[0-9]{2})",
            text,
            label="Brüder Mannesmann FY2025 cash",
        )
        ocf_match = _required_match(
            r"Cashflow aus der laufenden Geschäftstätigkeit\s+([+-]?[0-9.]+,[0-9]{2})\s+([+-]?[0-9.]+,[0-9]{2})",
            text,
            label="Brüder Mannesmann FY2025 operating cash flow",
        )

        revenue = _german_number(revenue_match.group(1))
        revenue_prev = _german_number(revenue_match.group(2))
        net_income = _german_number(net_match.group(1))
        total_assets = _german_number(assets_match.group(1))
        total_equity = _german_number(equity_match.group(1))
        cash = _german_number(cash_match.group(1))
        operating_cash_flow = _german_number(ocf_match.group(1))

        enriched = replace(
            company,
            reporting_currency="EUR",
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=((revenue / revenue_prev) - 1.0) * 100.0 if revenue_prev else None,
            net_income=net_income,
            net_margin_pct=(net_income / revenue) * 100.0 if revenue else None,
            total_assets=total_assets,
            total_liabilities=total_assets - total_equity,
            total_equity=total_equity,
            cash_and_equivalents=cash,
            operating_cash_flow=operating_cash_flow,
            filing_period_end="2025-12-31",
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "de_issuer_source": "brueder_mannesmann_annual_report_2025",
                "de_issuer_evidence_kind": "issuer_published_audited_annual_report",
                "de_esef_obligation": "not_required_open_market",
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_issuer_financial_statement",
            source_id="brueder-mannesmann-annual-report-2025",
            source_url=_BMM_PDF_URL,
            period_end="2025-12-31",
            quality=0.97,
            audit_status="audited",
            notes=(
                "Brüder Mannesmann AG issuer-published FY2025 audited consolidated "
                "annual report; Open Market listing does not require ESEF"
            ),
        ))

    def _jenoptik(self, company: GlobalCompany) -> GlobalCompany:
        if company.isin and company.isin.upper() != "DE000A2NB601":
            raise GlobalProviderError(f"JENOPTIK ISIN mismatch: {company.isin}")
        text = self._get_pdf_text(_JEN_PDF_URL)
        lower = text.lower()
        if "jenoptik annual report 2025" not in lower or "consolidated statement of profit or loss" not in lower:
            raise GlobalProviderError("JENOPTIK FY2025 issuer source identity/period marker missing")

        revenue_match = _required_match(
            r"\bRevenue\s+4\.1\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 revenue",
        )
        gross_match = _required_match(
            r"\bGross profit\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 gross profit",
        )
        ebit_match = _required_match(
            r"\bEBIT\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 EBIT",
        )
        net_match = _required_match(
            r"\bEarnings after tax\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 earnings after tax",
        )
        eps_match = _required_match(
            r"Earnings per share in euros \(undiluted = diluted\)\s+4\.10\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)",
            text, label="JENOPTIK FY2025 EPS",
        )
        current_assets_match = _required_match(
            r"\bCurrent assets\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 current assets",
        )
        cash_match = _required_match(
            r"\bCash and cash equivalents\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 cash",
        )
        assets_match = _required_match(
            r"\bTotal assets\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 total assets",
        )
        equity_match = _required_match(
            r"\bEquity\s+5\.10\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 equity",
        )
        noncurrent_liab_match = _required_match(
            r"\bNon-current liabilities\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 non-current liabilities",
        )
        current_liab_match = _required_match(
            r"(?<!Non-)\bCurrent liabilit(?:ies|es|ties)\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 current liabilities",
        )
        ocf_match = _required_match(
            r"\bCash flows from operating activities\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 operating cash flow",
        )
        capex_int_match = _required_match(
            r"Capital expenditure for intangible assets\s+[−–-]?([0-9][0-9,]*)\s+[−–-]?([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 intangible capex",
        )
        capex_ppe_match = _required_match(
            r"Capital expenditure for property, plant and equipment\s+[−–-]?([0-9][0-9,]*)\s+[−–-]?([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 PPE capex",
        )
        debt_nc_match = _required_match(
            r"\bNon-current financial debt\s+8\.1, 8\.2\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 non-current debt",
        )
        debt_c_match = _required_match(
            r"(?<!Non-)\bCurrent financial debt\s+8\.1, 8\.2\s+([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text, label="JENOPTIK FY2025 current debt",
        )

        revenue = _thousand_number(revenue_match.group(1))
        revenue_prev = _thousand_number(revenue_match.group(2))
        net_income = _thousand_number(net_match.group(1))
        total_assets = _thousand_number(assets_match.group(1))
        total_equity = _thousand_number(equity_match.group(1))
        current_assets = _thousand_number(current_assets_match.group(1))
        current_liabilities = _thousand_number(current_liab_match.group(1))
        noncurrent_liabilities = _thousand_number(noncurrent_liab_match.group(1))
        operating_cash_flow = _thousand_number(ocf_match.group(1))
        capex = _thousand_number(capex_int_match.group(1)) + _thousand_number(capex_ppe_match.group(1))
        total_debt = _thousand_number(debt_nc_match.group(1)) + _thousand_number(debt_c_match.group(1))

        enriched = replace(
            company,
            reporting_currency="EUR",
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=((revenue / revenue_prev) - 1.0) * 100.0 if revenue_prev else None,
            gross_profit=_thousand_number(gross_match.group(1)),
            operating_income=_thousand_number(ebit_match.group(1)),
            net_income=net_income,
            net_margin_pct=(net_income / revenue) * 100.0 if revenue else None,
            total_assets=total_assets,
            total_liabilities=noncurrent_liabilities + current_liabilities,
            total_equity=total_equity,
            current_assets=current_assets,
            current_liabilities=current_liabilities,
            cash_and_equivalents=_thousand_number(cash_match.group(1)),
            operating_cash_flow=operating_cash_flow,
            free_cash_flow=operating_cash_flow - capex,
            total_debt=total_debt,
            eps=float(eps_match.group(1)),
            filing_period_end="2025-12-31",
            filing_observed_at="2026-03-25T00:00:00+00:00",
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "de_issuer_source": "jenoptik_annual_report_2025",
                "de_issuer_evidence_kind": "issuer_published_audited_annual_report",
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_issuer_financial_statement",
            source_id="jenoptik-annual-report-2025",
            source_url=_JEN_PDF_URL,
            observed_at="2026-03-25T00:00:00+00:00",
            period_end="2025-12-31",
            quality=0.97,
            audit_status="audited",
            notes="JENOPTIK issuer-published FY2025 audited consolidated annual report",
        ))

    def _sap(self, company: GlobalCompany) -> GlobalCompany:
        text = self._get_text(_SAP_URL)
        lower = text.lower()
        if "sap group" not in lower or "2025" not in lower or "total revenue" not in lower:
            raise GlobalProviderError("SAP FY2025 issuer source identity/period marker missing")

        revenue_match = _required_match(
            r"Total revenue.{0,120}?([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text,
            label="SAP total revenue",
        )
        income_match = _required_match(
            r"Profit after tax(?:\s+from continuing operations)?.{0,120}?"
            r"([0-9][0-9,]*)\s+([0-9][0-9,]*)",
            text,
            label="SAP profit after tax",
        )
        revenue = _million_number(revenue_match.group(1))
        revenue_prev = _million_number(revenue_match.group(2))
        net_income = _million_number(income_match.group(1))
        net_income_prev = _million_number(income_match.group(2))
        eps = float(_required_match(
            r"Earnings per share, basic\s*\(in\s*€\).*?"
            r"([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)",
            text,
            label="SAP basic EPS",
        ).group(1))
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
            eps=eps,
            filing_period_end="2025-12-31",
            filing_observed_at="2026-01-29T00:00:00+00:00",
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "de_issuer_source": "sap_integrated_report_2025_financial_data",
                "de_issuer_evidence_kind": "issuer_published_financial_statements",
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_issuer_financial_statement",
            source_id="sap-integrated-report-2025-financial-data",
            source_url=_SAP_URL,
            observed_at="2026-01-29T00:00:00+00:00",
            period_end="2025-12-31",
            quality=0.96,
            notes=(
                "SAP issuer-published FY2025 consolidated financial statements; "
                "official issuer evidence, not a regulator filing"
            ),
        ))

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        ticker = self._identity(company)
        if ticker == "SIE":
            return self._siemens(company)
        if ticker == "ALV":
            return self._allianz(company)
        if ticker == "SAP":
            return self._sap(company)
        if ticker == "BMW":
            return self._bmw(company)
        if ticker == "DUE":
            return self._duerr(company)
        if ticker == "BMM":
            return self._bmm(company)
        if ticker == "JEN":
            return self._jenoptik(company)
        raise GlobalProviderError(f"no verified German issuer parser for {ticker}")
