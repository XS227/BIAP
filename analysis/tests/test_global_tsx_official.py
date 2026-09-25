from global_markets.tsx_official import parse_tmx_issuer_rows


HEADER = [
    "Co_ID", "Exchange", "Name", "Root\nTicker", "Market Cap (C$)",
    "O/S Shares", "Interlisted I", "Interlisted II", "Sector", "Sub\nSector",
    "HQ\nLocation", "HQ\nRegion", "Listing Type", "Listing Date",
    "Trading on OTC", "TSX Venture Grad", "Former CPC", "S&P/TSX Index",
    "Clean Technology Primary Industry", "Clean Technology Sub-Sector",
    "Consumer Products & Services Sub-Sector", "Life Sciences Sub-Sector",
    "Real Estate Sub-Sector", "Technology Sub-Sector", "USA City",
    "Asia Region", "Israel Related", "Fund Family/Issuing Entity", "SP_Type", "SP_Sub",
]


def row(*, exchange="TSX", name="Acme Inc.", ticker="ACM", sector="Technology",
        hq_region="Canada", listing_type="IPO", fund_family=None, sp_type=None, sp_sub=None):
    values = [None] * len(HEADER)
    mapping = {str(v).replace("\n", " ").strip(): i for i, v in enumerate(HEADER)}
    def put(key, value):
        values[mapping[key]] = value
    put("Co_ID", "X-1")
    put("Exchange", exchange)
    put("Name", name)
    put("Root Ticker", ticker)
    put("Sector", sector)
    put("HQ Region", hq_region)
    put("HQ Location", "ON")
    put("Listing Type", listing_type)
    put("Fund Family/Issuing Entity", fund_family)
    put("SP_Type", sp_type)
    put("SP_Sub", sp_sub)
    return values


def test_tmx_parser_keeps_domestic_operating_company():
    rows = parse_tmx_issuer_rows([["metadata"], HEADER, row()], exchange="TSX")
    assert len(rows) == 1
    assert rows[0].ticker == "ACM"
    assert rows[0].mic_code == "XTSE"
    assert rows[0].raw_provider_fields["official_universe"] is True


def test_tmx_parser_rejects_etf_cdr_fund_and_foreign_secondary_listing():
    samples = [
        row(name="Bitcoin ETF", ticker="BTCQ", sector="ETP", fund_family="3iQ", sp_type="Exchange Traded Funds"),
        row(name="AbbVie CDR", ticker="ABBV", sector="CDR", fund_family="CIBC", sp_type="CDR"),
        row(name="Bond Trust", ticker="IGBT", sector="Closed-End Funds", sp_type="Fund of Debt", sp_sub="FI Trust"),
        row(name="Foreign Issuer", ticker="FAP", sector="Financial Services", hq_region="USA"),
    ]
    assert parse_tmx_issuer_rows([HEADER, *samples, row()], exchange="TSX")[0].ticker == "ACM"


def test_tmx_parser_rejects_active_cpc_shells_on_tsxv():
    shell = row(exchange="TSXV", name="Capital Pool Corp.", ticker="POOL.P", sector="CPC", listing_type="IPO/CPC")
    operating = row(exchange="TSXV", name="Mining Co.", ticker="MINE", sector="Mining", listing_type="Other")
    rows = parse_tmx_issuer_rows([HEADER, shell, operating], exchange="TSXV")
    assert [item.ticker for item in rows] == ["MINE"]
    assert rows[0].mic_code == "XTSX"
