from global_markets.adx_official import parse_adx_issuers


def test_adx_parser_keeps_listed_main_and_growth_equities_only():
    payload = {
        "response": {
            "issuers": [
                {"dSymbol":"ADCB","nameEnglish":"Abu Dhabi Commercial Bank","isin":"AEA000201011","sectorNameEnglish":"Financials","status":"L","xMarketCode":"EQTY","marketCode":"510"},
                {"dSymbol":"ANAN","nameEnglish":"ANAN INVESTMENT HOLDING P.J.S.C","isin":"AEW000201015","sectorNameEnglish":"Real Estate","status":"L","xMarketCode":"PRCN","marketCode":"517"},
                {"dSymbol":"AGIX","nameEnglish":"KraneShares AI ETF","isin":"US5007673636","sectorNameEnglish":"Other","status":"L","xMarketCode":"FUND","marketCode":"515"},
                {"dSymbol":"ADCBRI25","nameEnglish":"ADCB Rights Issue 2025","isin":"AER01775A253","sectorNameEnglish":"Financials","status":"D","xMarketCode":"EQTY","marketCode":"510"},
            ]
        },
        "resultCode": "S",
        "resultMessage": "Success",
    }
    rows = parse_adx_issuers(payload)
    assert [row.ticker for row in rows] == ["ADCB", "ANAN"]
    assert rows[0].mic_code == "XADS"
    assert rows[0].isin == "AEA000201011"
    assert rows[0].raw_provider_fields["trusted_official_equity"] is True
    assert rows[1].raw_provider_fields["adx_market_code"] == "PRCN"
