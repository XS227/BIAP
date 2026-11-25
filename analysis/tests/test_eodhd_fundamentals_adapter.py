import pytest

from global_markets import eodhd_fundamentals as ef
from global_markets.providers import GlobalProviderError

PAYLOAD = {"General": {"Sector": "Technology", "CurrencyCode": "EUR"},
           "Highlights": {"MarketCapitalization": 1.5e11, "PERatio": 28.4, "EBITDA": 9e9},
           "Valuation": {"EnterpriseValueEbitda": 14.2},
           "Financials": {"Income_Statement": {"yearly": {"2023-12-31": {"totalRevenue": 1, "netIncome": 1}, "2024-12-31": {"totalRevenue": 3.1e10, "operatingIncome": 7e9, "netIncome": 5.2e9, "ebitda": 9e9, "interestExpense": 1.2e8}}},
                          "Balance_Sheet": {"yearly": {"2024-12-31": {"totalAssets": 6e10, "totalStockholderEquity": 3e10, "shortTermDebt": 1e9, "longTermDebt": 5e9}}},
                          "Cash_Flow": {"yearly": {"2024-12-31": {"totalCashFromOperatingActivities": 8e9, "capitalExpenditures": -2e9}}}}}


def test_disabled_by_default_and_nothing_is_requested(monkeypatch):
    monkeypatch.delenv(ef.FLAG, raising=False); monkeypatch.delenv(ef.TOKEN_ENV, raising=False)
    assert ef.enabled() is False
    with pytest.raises(GlobalProviderError):
        ef.fetch_fundamentals("SAP", "XETRA", client=object())
    monkeypatch.setenv(ef.FLAG, "1")
    assert ef.enabled() is False  # a token is required too


def test_payload_maps_to_the_completeness_fields_using_the_newest_year():
    f = ef.to_company_fields(PAYLOAD)
    assert f["revenue"] == 3.1e10 and f["total_debt"] == 6e9 and f["free_cash_flow"] == 6e9 and f["statement_period_end"] == "2024-12-31"
    c = ef.completeness_of(PAYLOAD)
    assert c["coreComplete"] and c["valuationComplete"] and c["coveragePct"] == 100.0


def test_missing_fields_stay_missing_and_lower_coverage():
    thin = {"Highlights": {"MarketCapitalization": 1e9}, "Financials": {"Balance_Sheet": {"yearly": {"2024-12-31": {"totalAssets": 5}}}}}
    c = ef.completeness_of(thin)
    assert not c["coreComplete"] and "revenue" in c["missing"] and c["coveragePct"] < 50
    assert ef.to_company_fields({})["revenue"] is None


def test_exchange_codes_cover_the_ten_markets():
    for ex in ("XETRA", "BME_MADRID", "EURONEXT_PARIS", "EURONEXT_AMSTERDAM", "EURONEXT_MILAN", "NASDAQ_STOCKHOLM", "EURONEXT_OSLO", "NASDAQ_HELSINKI", "LSE", "NASDAQ"):
        assert ef.EODHD_EXCHANGE[ex]
