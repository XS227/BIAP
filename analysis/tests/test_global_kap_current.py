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
