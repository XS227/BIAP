import pytest
import codal_data as codal


def test_empty_relay_with_verified_years_is_unavailable(monkeypatch):
    codal._financial_filings_cache.clear()
    codal._years_cache['فولاد'] = (codal.time.time(), ['1404/12/29'])
    monkeypatch.setattr(codal, '_get_json', lambda path, params=None: {'Letters': []})
    with pytest.raises(codal.CodalDataUnavailable, match='relay/search source'):
        codal.latest_financial_filings('فولاد')
    assert 'فولاد' not in codal._financial_filings_cache
    codal._years_cache.pop('فولاد', None)
