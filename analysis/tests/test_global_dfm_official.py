from global_markets.dfm_official import parse_dfm_equities


def test_dfm_parser_keeps_active_dfm_equities_only():
    payload=[
        {"ID":"1","SecuritySymbol":"DFM","FullName":"Dubai Financial Market PJSC","Exchange":"DFM","Active":True,"SecurityType":"Equity","Sector":"Financials"},
        {"ID":"2","SecuritySymbol":"OLD","FullName":"Old Co","Exchange":"DFM","Active":False,"SecurityType":"Equity"},
        {"ID":"3","SecuritySymbol":"NDX","FullName":"Nasdaq Dubai Co","Exchange":"Nasdaq Dubai","Active":True,"SecurityType":"Equity"},
        {"ID":"4","SecuritySymbol":"BOND","FullName":"Bond","Exchange":"DFM","Active":True,"SecurityType":"Bond"},
    ]
    rows=parse_dfm_equities(payload)
    assert [row.ticker for row in rows] == ["DFM"]
    assert rows[0].mic_code == "XDFM"
    assert rows[0].currency == "AED"
    assert rows[0].raw_provider_fields["official_universe"] is True
