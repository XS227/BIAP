import pytest
from global_markets.enel_issuer_esef import EnelIssuerESEFProvider, ENEL_LEI
from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError


def _company(**changes):
    data = dict(country='IT', exchange='EURONEXT_MILAN', ticker='ENEL',
                name='ENEL SPA', currency='EUR', isin='IT0003128367', lei=ENEL_LEI)
    data.update(changes)
    return GlobalCompany(**data)


def test_enel_only_accepts_exact_identity():
    provider = EnelIssuerESEFProvider()
    assert provider._resolve_lei(_company())[0] == ENEL_LEI
    for bad in (dict(ticker='OTHER'), dict(lei='OTHER'), dict(isin='IT0000000000'),
                dict(country='FR'), dict(name='OTHER SPA')):
        with pytest.raises(GlobalProviderError):
            provider._resolve_lei(_company(**bad))


def test_enel_official_package_is_pinned():
    provider = EnelIssuerESEFProvider()
    filings = provider.locators['IT'].annual_filings(_company(), ENEL_LEI, 'ENEL SPA')
    assert len(filings) == 1
    assert filings[0].package_url.startswith('https://www.enel.com/')
    assert provider.locators['IT'].annual_filings(_company(), 'OTHER', 'ENEL SPA') == []


def test_issuer_provenance_never_mislabeled_as_oam(monkeypatch):
    from global_markets.models import SourceEvidence
    from global_markets.oam_esef import NationalOAMESEFProvider
    def parsed(self, company):
        company.sources.append(SourceEvidence(
            provider='official-oam-it-enel-issuer',
            source_type='official_regulatory_xbrl',
            source_id='enel-issuer-esef-fy2025-v1',
            period_end='2025-12-31',
        ))
        company.raw_provider_fields.update(oam='it-enel-issuer', oam_document_id='enel-issuer-esef-fy2025-v1')
        return company
    monkeypatch.setattr(NationalOAMESEFProvider, 'enrich_fundamentals', parsed)
    result = EnelIssuerESEFProvider().enrich_fundamentals(_company())
    assert result.sources[0].source_type == 'official_issuer_financial_statement'
    assert result.sources[0].provider == 'it-enel-issuer-esef-fy2025'
    assert result.sources[0].provenance_status == 'independently_verified'
    assert 'oam' not in result.raw_provider_fields
    assert result.raw_provider_fields['issuer_report_lei_verified'] is True
