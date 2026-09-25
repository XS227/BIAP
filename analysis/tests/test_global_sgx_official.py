from global_markets.sgx_official import parse_sgx_prices


def test_sgx_parser_keeps_stock_rows_only():
    payload={"data":{"prices":[
        {"type":"stocks","nc":"D05","cn":"DBS Group Holdings Ltd"},
        {"type":"etfs","nc":"ES3","cn":"ETF"},
        {"type":"companywarrants","nc":"ABCW","cn":"Warrant"},
        {"type":"stocks","nc":"O39","cn":"OCBC Bank"},
    ]}}
    rows=parse_sgx_prices(payload)
    assert [r.ticker for r in rows] == ["D05","O39"]
    assert all(r.currency=="SGD" and r.mic_code=="XSES" for r in rows)
    assert all(r.raw_provider_fields["official_universe"] is True for r in rows)
