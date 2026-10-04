import codal_data as codal


def test_verified_financial_years_survive_missing_issuer_search(monkeypatch):
    monkeypatch.setattr(codal, 'find_company', lambda symbol: None)
    monkeypatch.setattr(codal, 'financial_years', lambda symbol: ['1404'])
    monkeypatch.setattr(codal, 'latest_filings', lambda symbol, limit: [])
    monkeypatch.setattr(codal, 'latest_financial_filings', lambda symbol, limit: [])
    metadata = codal.metadata_for_symbol('فولاد')
    assert metadata is not None
    assert metadata.financial_years == ['1404']
    assert metadata.company_id is None


def test_no_evidence_does_not_create_metadata(monkeypatch):
    monkeypatch.setattr(codal, 'find_company', lambda symbol: None)
    monkeypatch.setattr(codal, 'financial_years', lambda symbol: [])
    monkeypatch.setattr(codal, 'latest_filings', lambda symbol, limit: [])
    monkeypatch.setattr(codal, 'latest_financial_filings', lambda symbol, limit: [])
    assert codal.metadata_for_symbol('فولاد') is None
