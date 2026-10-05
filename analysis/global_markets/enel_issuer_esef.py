"""Exact-identity Enel issuer-published FY2025 ESEF fallback.

Uses the shared ESEF fact extractor, requiring the package's embedded entity LEI
and annual IFRS facts to match. No vendor facts are promoted to official.
"""
from dataclasses import replace
from .models import GlobalCompany
from .oam_esef import NationalOAMESEFProvider, OAMFiling
from .providers import GlobalProviderError

ENEL_LEI = 'WOCMU6HCI0OJWNPRZS33'
ENEL_URL = ('https://www.enel.com/content/dam/enel-com/documenti/investitori/'
            'informazioni-finanziarie/2025/annuali/en/integrated-annual-report-2025-ixbrl.zip')


class _EnelLocator:
    country = 'IT'

    def annual_filings(self, company, lei, legal_name):
        if lei.upper() != ENEL_LEI:
            return []
        return [OAMFiling(
            oam='it-enel-issuer', document_id='enel-issuer-esef-fy2025-v1',
            package_url=ENEL_URL,
            landing_url='https://www.enel.com/investors/financials',
            label='Issuer-published FY2025 ESEF package',
        )]


class EnelIssuerESEFProvider(NationalOAMESEFProvider):
    provider_id = 'it-enel-issuer-esef-fy2025'

    def __init__(self):
        super().__init__(timeout=120.0, locators=[_EnelLocator()])

    def _resolve_lei(self, company):
        if (company.country.upper() != 'IT' or company.ticker.upper() != 'ENEL'
                or (company.lei and company.lei.upper() != ENEL_LEI)
                or (company.isin and company.isin.upper() != 'IT0003128367')
                or 'ENEL' not in company.name.upper()):
            raise GlobalProviderError('Enel issuer ESEF identity mismatch')
        return ENEL_LEI, company.name

    def enrich_fundamentals(self, company):
        # Reuse verified package parsing but classify issuer hosting accurately.
        result = super().enrich_fundamentals(company)
        sources = [
            replace(source, provider=self.provider_id,
                    source_type='official_issuer_financial_statement',
                    source_url='https://www.enel.com/investors/financials',
                    notes=('Enel issuer-published FY2025 ESEF iXBRL; '
                           'embedded reporting LEI independently matched; '
                           'issuer publication, not national OAM filing'),
                    provenance_status='independently_verified',
                    audit_status='unknown')
            if source.source_id == 'enel-issuer-esef-fy2025-v1' else source
            for source in result.sources
        ]
        raw = dict(result.raw_provider_fields)
        raw['issuer_report_url'] = ENEL_URL
        raw['issuer_report_lei_verified'] = True
        for key in tuple(raw):
            if key.startswith('oam_') or key == 'oam':
                raw.pop(key)
        return replace(result, sources=sources, raw_provider_fields=raw)
