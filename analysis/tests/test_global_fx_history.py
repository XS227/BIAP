import json
from datetime import date, timedelta

import pytest

from global_markets import fx_history
from global_markets.fx_history import ECBHistoricalFX, parse_ecb_history
from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError
from global_markets.service import _derive_metrics

XML = """<gesmes:Envelope><Cube>
<Cube time='2025-12-31'><Cube currency='USD' rate='1.1750'/><Cube currency='SEK' rate='10.8000'/><Cube currency='GBP' rate='0.8700'/></Cube>
<Cube time='2025-12-30'><Cube currency='USD' rate='1.1700'/><Cube currency='SEK' rate='10.9000'/><Cube currency='GBP' rate='0.8650'/></Cube>
</Cube></gesmes:Envelope>"""


def _table(rates_by_day):
    return {d.isoformat(): r for d, r in rates_by_day.items()}


def _write_cache(path, table):
    path.write_text(json.dumps({"rates": table, "fetchedAt": "2026-01-01T00:00:00+00:00"}))


def _year(sek_start, sek_end, end=date(2025, 12, 31)):
    """Business days of the fiscal year with SEK drifting linearly start->end."""
    days = [end - timedelta(days=i) for i in range(364, -1, -1) if (end - timedelta(days=i)).weekday() < 5]
    n = len(days)
    return {d: {"SEK": sek_start + (sek_end - sek_start) * i / (n - 1), "USD": 1.1} for i, d in enumerate(days)}


def test_parse_ecb_history_reads_dated_fixings():
    table = parse_ecb_history(XML)
    assert table["2025-12-31"]["SEK"] == 10.8
    assert set(table) == {"2025-12-31", "2025-12-30"}


def test_spot_uses_latest_fixing_not_after_date_and_cross_rate(tmp_path):
    path = tmp_path / "h.json"
    _write_cache(path, parse_ecb_history(XML))
    fx = ECBHistoricalFX(path)
    q = fx.rate("USD", "SEK", date(2025, 12, 31))
    assert q.rate == pytest.approx(10.8 / 1.175)
    assert q.rate_date == "2025-12-31" and q.provider == fx_history.PROVIDER_ID
    # Saturday 2026-01-03 has no fixing: the previous published day is used, never a later one.
    assert fx.rate("EUR", "SEK", date(2026, 1, 3)).rate_date == "2025-12-31"
    assert fx.rate("EUR", "EUR", date(2025, 1, 1)).rate == 1.0


def test_spot_refuses_stale_and_missing_dates(tmp_path):
    path = tmp_path / "h.json"
    _write_cache(path, parse_ecb_history(XML))
    fx = ECBHistoricalFX(path)
    with pytest.raises(GlobalProviderError):
        fx.rate("EUR", "SEK", date(2026, 3, 1))      # > 7 days after the last fixing
    with pytest.raises(GlobalProviderError):
        fx.rate("EUR", "SEK", date(2025, 12, 1))     # before the first fixing
    with pytest.raises(GlobalProviderError):
        fx.rate("EUR", "XXX", date(2025, 12, 31))    # currency not published


def test_average_is_mean_of_window_and_requires_coverage(tmp_path):
    path = tmp_path / "h.json"
    table = _table(_year(10.0, 12.0))
    _write_cache(path, table)
    fx = ECBHistoricalFX(path)
    q = fx.average("EUR", "SEK", date(2025, 1, 1), date(2025, 12, 31))
    assert q.rate == pytest.approx(11.0, abs=0.02)
    assert q.kind == "period_average" and q.observations > 240
    with pytest.raises(GlobalProviderError):
        fx.average("EUR", "SEK", date(2023, 1, 1), date(2023, 12, 31))


def test_refresh_writes_compact_cache_and_rejects_thin_payload(tmp_path):
    fx = ECBHistoricalFX(tmp_path / "x.json")
    with pytest.raises(GlobalProviderError):
        fx.refresh(xml_text=XML)
    day = lambda d, r: f"<Cube time='{d}'><Cube currency='SEK' rate='{r}'/></Cube>"
    many = "".join(day((date.today() - timedelta(days=i)).isoformat(), 11.0) for i in range(260))
    meta = fx.refresh(xml_text=many)
    assert meta["days"] == 260
    assert ECBHistoricalFX(tmp_path / "x.json").available()


def _company(**kw):
    base = dict(country="SE", exchange="NASDAQ_STOCKHOLM", mic_code="XSTO", currency="SEK", ticker="TEST", name="Test AB",
                price=100.0, reporting_currency="EUR", filing_period_end="2025-12-31", shares_outstanding=10_000_000,
                total_equity=500_000_000, eps=3.0, net_income=30_000_000, ebitda=100_000_000, total_debt=200_000_000,
                cash_and_equivalents=50_000_000)
    base.update(kw)
    return GlobalCompany(**base)


@pytest.fixture
def fx_cache(tmp_path, monkeypatch):
    path = tmp_path / "fx.json"
    _write_cache(path, _table(_year(11.0, 11.0)))   # flat SEK 11.0 all year ... 
    table = json.loads(path.read_text())["rates"]
    table["2025-12-31"]["SEK"] = 10.0               # but 10.0 on the balance-sheet date
    _write_cache(path, table)
    monkeypatch.setenv("BIAP_GLOBAL_FX_HISTORY_PATH", str(path))
    return path


def test_cross_currency_ratios_use_date_aligned_rates(fx_cache):
    out = _derive_metrics(_company())
    # EPS is a flow (mean ~11.0): 3.0 EUR -> ~33 SEK => P/E ~ 100/33
    assert out.pe == pytest.approx(100.0 / (3.0 * 11.0), rel=0.01)
    # Equity is an instant at 31 Dec (10.0): 500m EUR -> 5,000m SEK; BVPS 500 SEK => P/B 0.2
    assert out.pb == pytest.approx(100.0 / 500.0, rel=1e-6)
    # EV = 1,000m SEK + 200m*10 - 50m*10 = 2,500m; EBITDA = 100m*11 = 1,100m
    assert out.ev_ebitda == pytest.approx(2_500_000_000 / 1_100_000_000, rel=0.01)
    notes = out.raw_provider_fields["derived_metrics"]
    assert any(n.startswith("fx_converted:EUR->SEK") for n in notes)
    fxc = out.raw_provider_fields["fx_conversion"]
    assert fxc["balance"]["rate_date"] == "2025-12-31" and fxc["flow"]["kind"] == "period_average"
    assert out.eps == 3.0 and out.total_equity == 500_000_000   # filing values keep reporting currency


def test_cross_currency_without_rate_stays_suppressed_with_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_FX_HISTORY_PATH", str(tmp_path / "missing.json"))
    out = _derive_metrics(_company())
    assert out.pe is None and out.pb is None and out.ev_ebitda is None
    assert any(n.startswith("fx_unavailable:fx_history_cache_unavailable") for n in out.raw_provider_fields["derived_metrics"])


def test_cross_currency_without_period_end_is_not_converted(fx_cache):
    out = _derive_metrics(_company(filing_period_end=None))
    assert out.pe is None and out.pb is None
    assert any("fx_unavailable:filing_period_end_missing" in n for n in out.raw_provider_fields["derived_metrics"])


def test_share_count_consistency_uses_reporting_currency_eps(fx_cache):
    # NI/EPS = 10m shares in reporting currency; a 40m count must still be withheld after FX conversion.
    out = _derive_metrics(_company(shares_outstanding=40_000_000))
    assert out.shares_outstanding is None
    assert any(n.startswith("shares_withheld") for n in out.raw_provider_fields["derived_metrics"])


def test_pb_from_exchange_market_cap_without_share_count():
    c = _company(currency="EUR", reporting_currency="EUR", shares_outstanding=None, market_cap=2_000_000_000,
                 total_equity=1_000_000_000, eps=None, ebitda=None)
    assert _derive_metrics(c).pb == pytest.approx(2.0)
