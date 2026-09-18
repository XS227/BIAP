from global_markets.scan_service import _global_top_markets


def test_global_top_markets_keep_verified_base_without_regulator_keys(monkeypatch):
    monkeypatch.delenv("BIAP_EDINET_API_KEY", raising=False)
    monkeypatch.delenv("BIAP_OPENDART_API_KEY", raising=False)
    markets = _global_top_markets()
    assert ("BR", "B3") in markets
    assert ("JP", "TSE_JP") not in markets
    assert ("KR", "KRX") not in markets
    assert len(markets) == 18


def test_global_top_markets_add_japan_and_korea_only_with_official_keys(monkeypatch):
    monkeypatch.setenv("BIAP_EDINET_API_KEY", "configured")
    monkeypatch.setenv("BIAP_OPENDART_API_KEY", "configured")
    markets = _global_top_markets()
    assert ("JP", "TSE_JP") in markets
    assert ("KR", "KRX") in markets
    assert len(markets) == 20
