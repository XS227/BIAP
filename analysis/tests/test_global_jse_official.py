from global_markets.jse_official import parse_jse_isin_full
from global_markets.yahoo_chart import YahooChartMarketProvider


MTN = "ZAE000042164MTN GROUP LIMITED                                      MTN Group Ltd                                                                                                  0000018336788680000000000000ZACOrdinary  MTN     000            1994/009584/06      9692942718     "
NASPERS = "ZAE000351946NASPERS LIMITED                                        Naspers Ltd -N-                                                                                                0000007650933430000000000000ZACNord      NPN     003            1925/001431/06      9550138714     "
ETF = "ZAE00032099010X FUND MANAGERS (RF) PROPRIETARY LIMITED             10X Income Actively Managed ETF                                                                                0000000746242640000000000000ZACETF       INCOME  000            2006/006498/07                     "


def test_jse_parser_keeps_only_ordinary_share_classes():
    rows = parse_jse_isin_full("\n".join([MTN, NASPERS, ETF]))
    assert [row.ticker for row in rows] == ["MTN", "NPN"]
    assert all(row.currency == "ZAR" and row.mic_code == "XJSE" for row in rows)
    assert rows[0].raw_provider_fields["jse_security_type"] == "Ordinary"
    assert rows[1].raw_provider_fields["jse_security_type"] == "Nord"


def test_yahoo_normalizes_south_african_cents():
    assert YahooChartMarketProvider._normalized_currency("ZAc") == ("ZAR", 0.01)
    assert YahooChartMarketProvider._normalized_currency("ZAC") == ("ZAR", 0.01)
