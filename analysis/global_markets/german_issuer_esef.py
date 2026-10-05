"""Issuer-published ESEF packages for German regulated-market issuers.

German issuers lodge their ESEF annual financial report with the
Unternehmensregister, whose robots.txt disallows automated search and
publication retrieval, and filings.xbrl.org indexes no German filings. Many
issuers also publish the identical ESEF package on their own investor-relations
site. This provider reads only those issuer-hosted packages, listed in a
reviewed registry (``data/de_issuer_esef.json``) keyed by ISIN.

Every registry row is re-verified on use exactly like a national OAM filing:
the package must carry inline XBRL, its embedded entity identifier must equal
the issuer's LEI, and it must contain annual IFRS duration facts. A row whose
package fails any gate blocks instead of falling back to guessed values, and
the evidence is labelled issuer publication, not regulator filing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .models import GlobalCompany
from .oam_esef import NationalOAMESEFProvider, OAMFiling
from .providers import GlobalProviderError

REGISTRY_PATH = Path(__file__).with_name("data") / "de_issuer_esef.json"

# Primary-market MICs of German EU regulated markets. Only issuers admitted to
# one of these must publish an ESEF annual financial report (WpHG §114); Open
# Market/Scale (Freiverkehr) listings have no ESEF obligation.
REGULATED_MICS = frozenset({"XFRA", "XETR", "XMUN", "XDUS", "XSTU", "XHAM", "XBER", "XHAN"})


@dataclass(frozen=True)
class IssuerPackage:
    isin: str
    lei: str
    ticker: str
    package_url: str
    landing_url: str
    period_end: str
    verified_at: str


def _https_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"issuer ESEF URL must be https: {url!r}")
    return parsed.netloc.lower()


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, IssuerPackage]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: dict[str, IssuerPackage] = {}
    for row in payload.get("issuers") or []:
        entry = IssuerPackage(**{k: str(row[k]).strip() for k in IssuerPackage.__dataclass_fields__})
        _https_host(entry.package_url)
        _https_host(entry.landing_url)
        if len(entry.lei) != 20 or not entry.isin.startswith("DE"):
            raise ValueError(f"invalid German issuer ESEF row {entry.isin}")
        if entry.isin in rows:
            raise ValueError(f"duplicate German issuer ESEF row {entry.isin}")
        rows[entry.isin] = entry
    return rows


@lru_cache(maxsize=1)
def _registry() -> dict[str, IssuerPackage]:
    return load_registry()


class _GermanIssuerLocator:
    country = "DE"

    def __init__(self, registry: dict[str, IssuerPackage]):
        self.by_lei = {row.lei.upper(): row for row in registry.values()}

    def annual_filings(self, company, lei, legal_name):
        row = self.by_lei.get(lei.upper())
        if row is None:
            return []
        return [OAMFiling(
            oam="de-issuer",
            document_id=f"de-issuer-esef:{row.isin}:{row.period_end}",
            package_url=row.package_url,
            landing_url=row.landing_url,
            label=f"Issuer-published ESEF annual financial report {row.period_end}",
            scope="consolidated",
        )]


class GermanIssuerESEFProvider(NationalOAMESEFProvider):
    provider_id = "de-issuer-esef-v1"

    def __init__(self, registry: Optional[dict[str, IssuerPackage]] = None):
        self.registry = registry if registry is not None else _registry()
        super().__init__(timeout=120.0, locators=[_GermanIssuerLocator(self.registry)])

    def _entry(self, company: GlobalCompany) -> IssuerPackage:
        if company.country.upper() != "DE":
            raise GlobalProviderError("German issuer ESEF applies to DE listings only")
        row = self.registry.get((company.isin or "").upper())
        if row is None:
            primary = str(company.raw_provider_fields.get("primary_market_mic") or "").upper()
            if primary and primary not in REGULATED_MICS:
                raise GlobalProviderError(
                    f"listing is not admitted to an EU regulated market (primary market {primary}): "
                    "no ESEF annual financial report obligation"
                )
            raise GlobalProviderError(
                f"no reviewed issuer-published ESEF package for {company.isin or company.ticker}"
            )
        if company.lei and company.lei.upper() != row.lei.upper():
            raise GlobalProviderError(
                f"German issuer ESEF LEI mismatch: listing {company.lei} != registry {row.lei}"
            )
        return row

    def _resolve_lei(self, company: GlobalCompany) -> tuple[str, str]:
        row = self._entry(company)
        return super()._resolve_lei(replace(company, lei=row.lei))

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        row = self._entry(company)
        result = super().enrich_fundamentals(company)
        document_id = f"de-issuer-esef:{row.isin}:{row.period_end}"
        sources = [
            replace(
                source,
                provider=self.provider_id,
                source_type="official_issuer_financial_statement",
                source_url=row.landing_url,
                notes=(
                    f"Issuer-published ESEF iXBRL ({urlparse(row.package_url).netloc}); "
                    f"embedded reporting LEI {row.lei} independently matched; "
                    "issuer publication of the report lodged with the Unternehmensregister"
                ),
                provenance_status="independently_verified",
                audit_status="unknown",
            )
            if source.source_id == document_id else source
            for source in result.sources
        ]
        raw = {k: v for k, v in result.raw_provider_fields.items() if not (k == "oam" or k.startswith("oam_"))}
        raw["issuer_report_url"] = row.package_url
        raw["issuer_report_lei_verified"] = True
        return replace(result, sources=sources, raw_provider_fields=raw)
