"""Reviewed FCA NSM annual-report snapshots for UK (LSE) equities.

Some LSE Main Market issuers -- typically investment trusts and shell
companies -- lodge their audited annual report on the FCA National Storage
Mechanism (the UK officially appointed mechanism) without inline XBRL, e.g. a
pdf2htmlEX conversion flagged "Untagged" by the NSM, or only as the RNS
audited-results announcement. BIAP's ESEF parsers correctly refuse those
documents, which left such issuers with vendor-only fundamentals.

Records live in data/gb_verified_annual_reports.json and are accepted only when:
* country is GB and the listing ISIN/ticker exactly match the reviewed record;
* the source is an HTTPS FCA NSM artefact (data.fca.org.uk/artefacts/NSM/...)
  pinned by pinned_document_sha256() of the reviewed document;
* period/currency/audit opinion are explicit, and the opinion is not adverse
  or a disclaimer;
* fundamentals contain only the supported normalized fields, and
  total_assets - total_liabilities == total_equity when all three are present.

The normalized numbers are transcribed from the primary statements of the
named audited NSM filing. This provider is a fallback behind the tagged
NSM/ESEF chain: a tagged filing for the same or a newer period always wins.
Shared validation and enrichment live in reviewed_annual_reports.py.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse

from .models import GlobalCompany
from .providers import GlobalProviderError
from .reviewed_annual_reports import DATA_DIR, ReviewedAnnualReportProvider

REGISTRY_PATH = DATA_DIR / "gb_verified_annual_reports.json"

_NSM_HOST = "data.fca.org.uk"
_NSM_PATH_PREFIX = "/artefacts/NSM/"

_CF_EMAIL = re.compile(rb'(/cdn-cgi/l/email-protection#|data-cfemail=")[0-9a-f]+')


def pinned_document_sha256(content: bytes) -> str:
    """SHA-256 used for registry pins.

    NSM RNS pages are served through Cloudflare, which re-randomizes its email
    obfuscation tokens on every request; only those tokens are blanked so the
    pin stays stable while any change to the filing text still breaks it.
    """
    return hashlib.sha256(_CF_EMAIL.sub(rb"\1", content)).hexdigest()


class UKReviewedNSMAnnualReportProvider(ReviewedAnnualReportProvider):
    provider_id = "gb-reviewed-fca-nsm-annual-report"
    country = "GB"
    registry_file = REGISTRY_PATH.name
    label = "UK reviewed annual-report"
    raw_prefix = "gb_reviewed"
    verification_mode = "reviewed_fca_nsm_annual_report"
    default_source_id_prefix = "FCA-NSM"

    @classmethod
    def row_key(cls, row: dict) -> str:
        return str(row.get("isin") or "").upper().strip()

    @classmethod
    def company_key(cls, company: GlobalCompany) -> str:
        return (company.isin or "").upper().strip()

    @classmethod
    def validate_jurisdiction(cls, row: dict, key: str) -> None:
        isin = key
        ticker = str(row.get("ticker") or "").upper().strip()
        url = str(row.get("sourceUrl") or "").strip()
        parsed = urlparse(url)
        if len(isin) != 12 or not isin.isalnum():
            raise ValueError(f"invalid UK reviewed annual-report ISIN {isin!r}")
        if not ticker:
            raise ValueError(f"UK reviewed annual-report row {isin} has no ticker")
        if parsed.scheme != "https" or parsed.netloc.lower() != _NSM_HOST or not parsed.path.startswith(_NSM_PATH_PREFIX):
            raise ValueError(f"UK reviewed annual-report URL is not an FCA NSM artefact: {url!r}")
        row["isin"] = isin
        row["ticker"] = ticker

    def wrong_country_message(self) -> str:
        return "UK reviewed NSM annual reports apply to GB listings only"

    def missing_message(self, company: GlobalCompany, key: str) -> str:
        return f"no reviewed FCA NSM annual-report snapshot for {key or company.ticker}"

    def check_identity(self, company: GlobalCompany, row: dict) -> None:
        if company.ticker.upper() != row["ticker"]:
            raise GlobalProviderError(
                f"UK reviewed annual-report ticker mismatch: {company.ticker} != {row['ticker']}"
            )
        expected_lei = str(row.get("lei") or "").upper().strip()
        if expected_lei and company.lei and company.lei.upper().strip() != expected_lei:
            raise GlobalProviderError(
                f"UK reviewed annual-report LEI mismatch: {company.lei} != {expected_lei}"
            )

    def jurisdiction_fields(self, company: GlobalCompany, row: dict) -> dict[str, Any]:
        expected_lei = str(row.get("lei") or "").upper().strip()
        return {"lei": company.lei or expected_lei or None}

    def raw_fields(self, row: dict) -> dict[str, Any]:
        return {"gb_reviewed_nsm_tagging": row.get("nsmTagging")}

    def notes(self, row: dict) -> str:
        return (
            "reviewed normalized values from the audited annual report lodged on the "
            f"FCA National Storage Mechanism without inline XBRL (sha256 {row['sha256'][:12]})"
        )


def _validate_row(raw: dict) -> dict:
    return UKReviewedNSMAnnualReportProvider.validate_row(raw)


def _registry() -> dict[str, dict[str, Any]]:
    return UKReviewedNSMAnnualReportProvider.load_registry()
