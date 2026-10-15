from __future__ import annotations

from global_markets.kap import parse_kap_financial_summary
from global_markets.runtime import build_registry


def _table(rows):
    body = []
    for row in rows:
        body.append('<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>')
    return '<table>' + ''.join(body) + '</table>'


def test_kap_summary_uses_latest_completed_annual_column_only():
    html = ''.join([
        _table([
            ['FİNANSAL DURUM TABLOSU', '2024/12', '2025/12', '2026/06'],
            ['Sunum Para Birimi', 'TL', 'TL', 'TL'],
            ['Finansal Tablo Niteliği', 'Konsolide', 'Konsolide', 'Konsolide'],
            ['Dönen Varlıklar', '1.000', '1.200', '1.500'],
            ['Toplam Varlıklar', '5.000', '6.000', '7.000'],
            ['Kısa Vadeli Yükümlülükler', '800', '900', '1.000'],
            ['Toplam Yükümlülükler', '2.000', '2.500', '3.000'],
            ['Toplam Özkaynaklar', '3.000', '3.500', '4.000'],
        ]),
        _table([
            ['KAR VEYA ZARAR VE DİĞER KAPSAMLI GELİR TABLOSU', '2024/12', '2025/12', '2026/06'],
            ['Sunum Para Birimi', '1000TL', '1000TL', '1000TL'],
            ['Finansal Tablo Niteliği', 'Konsolide', 'Konsolide', 'Konsolide'],
            ['Hasılat', '800', '1.000', '700'],
            ['Brüt Kâr (Zarar)', '240', '300', '200'],
            ['Esas Faaliyet Kârı (Zararı)', '160', '200', '120'],
            ['Net Dönem Kârı (Zararı)', '80', '100', '50'],
        ]),
        _table([
            ['NAKİT AKIŞ TABLOSU', '2024/12', '2025/12', '2026/06'],
            ['Sunum Para Birimi', '1000TL', '1000TL', '1000TL'],
            ['İşletme Faaliyetlerinden Nakit Akışları', '90', '110', '40'],
        ]),
    ])
    parsed = parse_kap_financial_summary(html)
    assert parsed['period'] == '2025/12'
    assert parsed['periodEnd'] == '2025-12-31'
    assert parsed['reportScope'] == 'consolidated'
    assert parsed['metrics']['total_assets'] == 6000.0
    assert parsed['metrics']['revenue'] == 1_000_000.0
    assert parsed['metrics']['revenue_prev'] == 800_000.0
    assert parsed['metrics']['revenue_yoy_pct'] == 25.0
    assert parsed['metrics']['net_income'] == 100_000.0
    assert parsed['metrics']['net_margin_pct'] == 10.0
    assert parsed['metrics']['operating_cash_flow'] == 110_000.0
    # 2026/06 values are deliberately not used as annual fundamentals.
    assert parsed['metrics']['revenue'] != 700_000.0


def test_runtime_registers_official_kap_for_turkiye(monkeypatch):
    monkeypatch.delenv('BIAP_GLOBAL_MARKET_API_KEY', raising=False)
    registry = build_registry()
    provider = registry.fundamentals('TR', 'BIST')
    assert 'kap-official-financial-summary' in provider.provider_id


def test_kap_get_retries_dropped_connections_then_succeeds(monkeypatch):
    import httpx
    from global_markets import kap

    monkeypatch.setattr(kap, "KAP_RETRY_BACKOFF_SEC", 0.0)
    calls = {"n": 0}

    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url):
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.RemoteProtocolError("Server disconnected")
            return httpx.Response(200, text="ok", request=httpx.Request("GET", url))

    monkeypatch.setattr(kap.httpx, "Client", FakeClient)
    assert kap.KAPFundamentalsProvider()._get("https://www.kap.org.tr/x") == "ok" and calls["n"] == 3


def test_kap_get_reports_transport_error_after_last_attempt_and_does_not_retry_404(monkeypatch):
    import httpx
    import pytest
    from global_markets import kap
    from global_markets.providers import GlobalProviderError

    monkeypatch.setattr(kap, "KAP_RETRY_BACKOFF_SEC", 0.0)
    calls = {"n": 0}
    status = {"code": None}

    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url):
            calls["n"] += 1
            if status["code"]:
                return httpx.Response(status["code"], request=httpx.Request("GET", url))
            raise httpx.RemoteProtocolError("Server disconnected")

    monkeypatch.setattr(kap.httpx, "Client", FakeClient)
    with pytest.raises(GlobalProviderError, match="KAP request failed: RemoteProtocolError"):
        kap.KAPFundamentalsProvider()._get("https://www.kap.org.tr/x")
    assert calls["n"] == kap.KAP_GET_ATTEMPTS
    calls["n"], status["code"] = 0, 404
    with pytest.raises(GlobalProviderError, match="HTTPStatusError"):
        kap.KAPFundamentalsProvider()._get("https://www.kap.org.tr/x")
    assert calls["n"] == 1
