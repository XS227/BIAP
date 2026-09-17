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
