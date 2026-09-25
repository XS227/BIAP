from global_markets.hkex_official import parse_hkex_securities_rows


def test_hkex_parser_keeps_primary_equities_only():
    rows = [
        ["List of Securities", None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
        ["Stock Code","Name of Securities","Category","Sub-Category","Board Lot","ISIN","Expiry Date","Subject to Stamp Duty","Shortsell Eligible","CAS Eligible","VCM Eligible","Admitted to CCASS","Debt Securities Board Lot (Nominal)","Debt Securities Investor Type","POS Eligible","Spread Table\n1 = Part A","Trading Currency","RMB Counter"],
        ["00005","HSBC HOLDINGS","Equity","Equity Securities (Main Board)","400","GB0005405286",None,"Y","Y","Y","Y","Y",None,None,"Y","1","HKD",None],
        ["08001","GEM COMPANY","Equity","Equity Securities (GEM)","1000","KYG000000001",None,"Y","N","N","N","Y",None,None,"N","1","HKD",None],
        ["80005","HSBC-R","Equity","Equity Securities (Main Board)","400","GB0005405286",None,"Y","Y","Y","Y","Y",None,None,"Y","1","RMB",None],
        ["02800","TRACKER FUND","Exchange Traded Products","Exchange Traded Funds","500","HK0000000000",None,"N","Y","Y","Y","Y",None,None,"Y","1","HKD",None],
        ["04621","CINDA 21USDPREF","Equity","Equity Securities (Main Board)","1","HK0000000001",None,"Y","N","N","N","Y",None,None,"N","1","USD",None],
        ["09999","INVESTCO","Equity","Investment Companies","100","HK0000000002",None,"Y","N","N","N","Y",None,None,"N","1","HKD",None],
    ]
    result = parse_hkex_securities_rows(rows)
    assert [row.ticker for row in result] == ["0005", "8001"]
    assert all(row.currency == "HKD" and row.mic_code == "XHKG" for row in result)
    assert result[0].isin == "GB0005405286"
    assert result[0].raw_provider_fields["official_universe"] is True
