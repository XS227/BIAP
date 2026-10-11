from __future__ import annotations

import json

from global_markets.cached_fundamentals import PersistentFundamentalsProvider
from global_markets.fallback_fundamentals import FallbackFundamentalsProvider
from global_markets.kap_current import KAPCurrentFundamentalsProvider, parse_kap_current_summary
from global_markets.runtime import build_registry


def _flight_html() -> str:
    rows = [
        '1:["$","tr",null,{"children":[["$","th","2024/12_1",{"children":"2024/12"}],["$","th","2025/12_2",{"children":"2025/12"}]]}]',
        '2:["$","tr",null,{"children":[["$","td",null,{"children":"Sunum Para Birimi"}],["$","td","bilanco_2024/12_1",{"children":"1000TL"}],["$","td","bilanco_2025/12_2",{"children":"1000TL"}]]}]',
        '3:["$","tr",null,{"children":[["$","td",null,{"children":"Finansal Tablo Niteliği"}],["$","td","bilanco_2024/12_1",{"children":"Konsolide"}],["$","td","bilanco_2025/12_2",{"children":"Konsolide"}]]}]',
        '4:["$","tr","ifrs-full_Assets",{"children":[["$","td",null,{"children":"Varlıklar Toplamı"}],["$","td","bilanco_2024/12_1",{"children":"2.653.105.361"}],["$","td","bilanco_2025/12_2",{"children":"3.558.949.685"}]]}]',
        '5:["$","tr","ifrs-full_Equity",{"children":[["$","td",null,{"children":"Özkaynaklar"}],["$","td","bilanco_2024/12_1",{"children":"240.383.648"}],["$","td","bilanco_2025/12_2",{"children":"310.169.116"}]]}]',
        '6:["$","tr","ifrs-full_ProfitLoss",{"children":[["$","td",null,{"children":"Net Dönem Kârı (Zararı)"}],["$","td","gelir_2024/12_1",{"children":"42.362.192"}],["$","td","gelir_2025/12_2",{"children":"57.224.231"}]]}]',
    ]
    flight = "\n".join(rows)
    return '<html><script>self.__next_f.push([1,' + json.dumps(flight, ensure_ascii=False) + '])</script></html>'


def test_current_kap_parser_reads_nextjs_flight_annual_cells():
    parsed = parse_kap_current_summary(_flight_html())
    assert parsed["period"] == "2025/12"
    assert parsed["periodEnd"] == "2025-12-31"
    assert parsed["previousPeriod"] == "2024/12"
    assert parsed["currency"] == "TRY"
    assert parsed["reportScope"] == "consolidated"
    assert parsed["transport"] == "nextjs-flight"
    assert parsed["metrics"]["total_assets"] == 3_558_949_685_000.0
    assert parsed["metrics"]["total_equity"] == 310_169_116_000.0
    assert parsed["metrics"]["net_income"] == 57_224_231_000.0


def test_runtime_uses_current_kap_provider(monkeypatch):
    monkeypatch.delenv("BIAP_GLOBAL_MARKET_API_KEY", raising=False)
    registry = build_registry()
    provider = registry.fundamentals("TR", "BIST")
    assert isinstance(provider, PersistentFundamentalsProvider)
    assert isinstance(provider.upstream, FallbackFundamentalsProvider)
    assert isinstance(provider.upstream.primary, KAPCurrentFundamentalsProvider)
    assert "kap-official-financial-summary" in provider.provider_id


def _semantic_balance_table() -> str:
    rows = [
        ["FİNANSAL DURUM TABLOSU", "2024/12", "2025/12", "2026/06"],
        ["Sunum Para Birimi", "1000TL", "1000TL", "1000TL"],
        ["Finansal Tablo Niteliği", "Konsolide", "Konsolide", "Konsolide"],
        ["Toplam Varlıklar", "352.221.005", "413.578.419", "495.799.575"],
        ["Toplam Yükümlülükler", "182.453.835", "194.574.186", "243.380.225"],
        ["Toplam Özkaynaklar", "169.767.170", "219.004.233", "252.419.350"],
    ]
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table>{body}</table>"


def _flight_income_rows(unit_cells: bool = True) -> str:
    # Current KAP (AEFES FY2025): header-style unit cells are keyed 2025_12_2,
    # value cells gelir_2025/12_2.
    rows = [
        '1:["$","tr",null,{"children":[["$","th","2024/12_1",{"children":"2024/12"}],["$","th","2025/12_2",{"children":"2025/12"}]]}]',
    ]
    if unit_cells:
        rows.append('2:["$","tr",null,{"children":[["$","td",null,{"children":"Sunum Para Birimi"}],[["$","td","2024_12_1",{"children":"1000TL"}],["$","td","2025_12_2",{"children":"1000TL"}]]]}]')
    rows += [
        '3:["$","tr",null,{"children":[["$","td",null,{"children":"Hasılat"}],[["$","td","gelir_2024/12_1",{"children":"231.354.487"}],["$","td","gelir_2025/12_2",{"children":"243.847.131"}]]]}]',
        '4:["$","tr",null,{"children":[["$","td",null,{"children":"Net Dönem Karı (Zararı)"}],[["$","td","gelir_2024/12_1",{"children":"23.344.801"}],["$","td","gelir_2025/12_2",{"children":"17.336.527"}]]]}]',
    ]
    return '<script>self.__next_f.push([1,' + json.dumps("\n".join(rows), ensure_ascii=False) + '])</script>'


def test_semantic_balance_sheet_is_merged_with_flight_income_statement():
    parsed = parse_kap_current_summary("<html>" + _semantic_balance_table() + _flight_income_rows() + "</html>")
    m = parsed["metrics"]
    assert parsed["transport"] == "semantic-html+nextjs-flight"
    assert m["total_assets"] == 413_578_419_000.0
    assert m["revenue"] == 243_847_131_000.0
    assert m["revenue_prev"] == 231_354_487_000.0
    assert m["net_income"] == 17_336_527_000.0
    assert round(m["net_margin_pct"], 2) == 7.11


def test_flight_rows_without_presentation_unit_are_not_read_as_plain_lira():
    import pytest
    from global_markets.providers import GlobalProviderError
    with pytest.raises(GlobalProviderError):
        parse_kap_current_summary("<html>" + _flight_income_rows(unit_cells=False) + "</html>")
    # With a semantic table present, the unitless Flight rows are ignored.
    parsed = parse_kap_current_summary("<html>" + _semantic_balance_table() + _flight_income_rows(unit_cells=False) + "</html>")
    assert "revenue" not in parsed["metrics"]


def test_unknown_kap_presentation_unit_fails_closed():
    import pytest
    from global_markets.kap import _currency_scale
    from global_markets.providers import GlobalProviderError
    assert _currency_scale("1000TL") == ("TRY", 1000.0)
    assert _currency_scale("1000 USD") == ("USD", 1000.0)
    with pytest.raises(GlobalProviderError):
        _currency_scale("Bin TL (x)")
