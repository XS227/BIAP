"""Reviewed SEC EDGAR annual-report snapshots for US-listed issuers.

US-listed registered closed-end funds (e.g. GAM, GAB on NYSE) file their
audited annual report on Form N-CSR. Its XBRL carries only the cef taxonomy
(fee table, leverage, NAV per share), so SEC companyfacts has no financial
statements for these CIKs and returns 404. BIAP's companyfacts and filed
instance readers therefore correctly find nothing.

Records live in data/us_verified_annual_reports.json and, on top of the
shared rules in reviewed_annual_reports.py, are accepted only when:
* country is US and the listing exchange/ticker exactly match the record;
* the form is an annual report (N-CSR, 10-K, 20-F, 40-F or an amendment);
* the source is an HTTPS EDGAR archive document under the record's own CIK
  and accession folder (www.sec.gov/Archives/edgar/data/<cik>/<accession>/);
* the listing name and the SEC filer name share the issuer's legal-name core,
  and any CIK already attached to the listing equals the record's CIK.

The provider is a fallback behind SEC companyfacts and the filed-instance
readers: an XBRL-tagged filing for the same or a newer period always wins.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse

from .models import GlobalCompany
from .providers import GlobalProviderError
from .reviewed_annual_reports import DATA_DIR, ReviewedAnnualReportProvider
from .sec_identity import sec_core

REGISTRY_PATH = DATA_DIR / "us_verified_annual_reports.json"

_EDGAR_HOST = "www.sec.gov"
_ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")
ANNUAL_FORMS = frozenset({
    "N-CSR", "N-CSR/A", "10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A",
})

# www.sec.gov is fronted by Akamai Bot Manager, which injects a rotating
# sensor <script> before </body> into every HTML response and, for clients it
# scores as undeclared automation, a head beacon and a <noscript> pixel too.
_AKAMAI_BEACONS = re.compile(
    rb'<script >[a-z]+="\d+"</script><script type="text/javascript" src="https://www\.sec\.gov/akam/[^"]+"\s*defer></script>'
    rb'|<noscript><img src="https://www\.sec\.gov/akam/[^"]+"[^>]*/></noscript>'
)
_AKAMAI_SENSOR = re.compile(rb'<script type="text/javascript"\s+src="/[A-Za-z0-9_\-/]+"></script>(?=</body>)')


def pinned_document_sha256(content: bytes) -> str:
    """SHA-256 used for registry pins of EDGAR archive documents.

    Only the CDN's bot-manager injections are removed, so the pin is the same
    for every client while any change to the filed document still breaks it.
    """
    return hashlib.sha256(_AKAMAI_SENSOR.sub(b"", _AKAMAI_BEACONS.sub(b"", content))).hexdigest()


class USReviewedSECAnnualReportProvider(ReviewedAnnualReportProvider):
    provider_id = "us-reviewed-sec-edgar-annual-report"
    country = "US"
    registry_file = REGISTRY_PATH.name
    label = "US reviewed annual-report"
    raw_prefix = "us_reviewed"
    verification_mode = "reviewed_sec_edgar_annual_report"
    default_source_id_prefix = "SEC-EDGAR"

    @classmethod
    def row_key(cls, row: dict) -> str:
        exchange = str(row.get("exchange") or "").upper().strip()
        ticker = str(row.get("ticker") or "").upper().strip()
        return f"{exchange}:{ticker}"

    @classmethod
    def company_key(cls, company: GlobalCompany) -> str:
        return f"{company.exchange.upper().strip()}:{company.ticker.upper().strip()}"

    @classmethod
    def validate_jurisdiction(cls, row: dict, key: str) -> None:
        exchange = str(row.get("exchange") or "").upper().strip()
        ticker = str(row.get("ticker") or "").upper().strip()
        if not exchange or not ticker:
            raise ValueError(f"US reviewed annual-report row {key!r} needs exchange and ticker")
        try:
            cik = int(row.get("cik"))
        except (TypeError, ValueError):
            raise ValueError(f"US reviewed annual-report row {key} has no SEC CIK") from None
        if cik <= 0:
            raise ValueError(f"US reviewed annual-report row {key} has no SEC CIK")
        accession = str(row.get("accession") or "").strip()
        if not _ACCESSION.match(accession):
            raise ValueError(f"US reviewed annual-report row {key} has invalid accession {accession!r}")
        form = str(row.get("form") or "").upper().strip()
        if form not in ANNUAL_FORMS:
            raise ValueError(f"US reviewed annual-report row {key} form {form!r} is not an annual report")
        legal_name = str(row.get("legalName") or "").strip()
        entity_name = str(row.get("secEntityName") or "").strip()
        if not legal_name or not entity_name or sec_core(legal_name) != sec_core(entity_name):
            raise ValueError(f"US reviewed annual-report row {key} legalName does not match secEntityName")
        url = str(row.get("sourceUrl") or "").strip()
        parsed = urlparse(url)
        folder = f"/Archives/edgar/data/{cik}/{accession.replace('-', '')}/"
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != _EDGAR_HOST
            or not parsed.path.startswith(folder)
            or len(parsed.path) <= len(folder)
        ):
            raise ValueError(
                f"US reviewed annual-report URL is not the EDGAR document of CIK {cik} accession {accession}: {url!r}"
            )
        row.update({"exchange": exchange, "ticker": ticker, "cik": cik, "accession": accession, "form": form})

    def wrong_country_message(self) -> str:
        return "US reviewed SEC annual reports apply to US listings only"

    def missing_message(self, company: GlobalCompany, key: str) -> str:
        return f"no reviewed SEC EDGAR annual-report snapshot for {key}"

    def check_identity(self, company: GlobalCompany, row: dict) -> None:
        listed = sec_core(company.name)
        if listed and listed not in {sec_core(row["legalName"]), sec_core(row["secEntityName"])}:
            raise GlobalProviderError(
                f"US reviewed annual-report issuer mismatch: {company.name!r} != {row['secEntityName']!r}"
            )
        attached = company.raw_provider_fields.get("sec_cik")
        if attached not in (None, ""):
            try:
                attached_cik = int(attached)
            except (TypeError, ValueError):
                attached_cik = None
            if attached_cik != row["cik"]:
                raise GlobalProviderError(
                    f"US reviewed annual-report CIK mismatch: {attached} != {row['cik']}"
                )

    def raw_fields(self, row: dict) -> dict[str, Any]:
        return {
            "sec_cik": row["cik"],
            "sec_form": row["form"],
            "sec_accession": row["accession"],
            "us_reviewed_xbrl_coverage": row.get("xbrlCoverage"),
        }

    def notes(self, row: dict) -> str:
        coverage = str(row.get("xbrlCoverage") or "no XBRL financial statements").strip()
        return (
            f"reviewed normalized values from the audited Form {row['form']} filed on SEC EDGAR "
            f"(accession {row['accession']}; {coverage}; sha256 {row['sha256'][:12]})"
        )
