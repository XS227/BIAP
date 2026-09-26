from global_markets.fallback_fundamentals import FallbackFundamentalsProvider
from global_markets.jse_issuer import parse_sibanye_2025_xbrl, JSEIssuerFundamentalsProvider
from global_markets.cached_fundamentals import PersistentFundamentalsProvider
from global_markets.runtime import build_registry


XML = b"""<xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:ifrs="urn:ifrs">
<xbrli:context id="FY25"><xbrli:entity/><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<ifrs:Revenue contextRef="FY25">129677000000</ifrs:Revenue>
<ifrs:ProfitLossAttributableToOwnersOfParent contextRef="FY25">-5171000000</ifrs:ProfitLossAttributableToOwnersOfParent>
<ifrs:Assets contextRef="FY25">149737000000</ifrs:Assets>
<ifrs:Liabilities contextRef="FY25">105570000000</ifrs:Liabilities>
<ifrs:Equity contextRef="FY25">44167000000</ifrs:Equity>
<ifrs:CashAndCashEquivalents contextRef="FY25">17178000000</ifrs:CashAndCashEquivalents>
</xbrl>"""


def test_sibanye_2025_xbrl_primary_totals_parse_and_reconcile():
    metrics = parse_sibanye_2025_xbrl(XML)
    assert metrics["revenue"] == 129_677_000_000.0
    assert metrics["net_income"] == -5_171_000_000.0
    assert metrics["total_assets"] == 149_737_000_000.0
    assert metrics["total_liabilities"] == 105_570_000_000.0
    assert metrics["total_equity"] == 44_167_000_000.0


def test_za_runtime_prefers_jse_current_filing_before_sec_and_vendor():
    provider = build_registry().fundamentals("ZA", "JSE")
    assert isinstance(provider, PersistentFundamentalsProvider)
    outer = provider.upstream
    assert isinstance(outer, FallbackFundamentalsProvider)
    official = outer.primary
    assert isinstance(official, FallbackFundamentalsProvider)
    assert isinstance(official.primary, JSEIssuerFundamentalsProvider)
