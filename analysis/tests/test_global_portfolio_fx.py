from datetime import date, timedelta

import pytest

import global_markets.fx as fx
from global_markets.providers import GlobalProviderError


def _xml(day, rates):
    cubes = "".join(f"<Cube currency='{c}' rate='{r}'/>" for c, r in rates.items())
    return f"<Envelope><Cube><Cube time='{day}'>{cubes}</Cube></Cube></Envelope>"


class _Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def _patch(monkeypatch, text):
    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            return _Resp(text)

    monkeypatch.setattr(fx.httpx, "Client", _Client)
    fx.ECBReferenceFXProvider._cache = None


def test_ecb_cross_rates_are_exact_and_dated(monkeypatch):
    day = date.today().isoformat()
    _patch(monkeypatch, _xml(day, {"USD": 1.12, "GBP": 0.85, "SEK": 11.2}))
    p = fx.ECBReferenceFXProvider()
    assert p.rate("GBP", "EUR") == pytest.approx(1 / 0.85)
    assert p.rate("USD", "GBP") == pytest.approx(0.85 / 1.12)
    assert p.rate("EUR", "EUR") == 1.0
    assert p.source_info()["rateDate"] == day


def test_ecb_refuses_stale_rates_and_unknown_currencies(monkeypatch):
    _patch(monkeypatch, _xml((date.today() - timedelta(days=30)).isoformat(), {"USD": 1.12}))
    with pytest.raises(GlobalProviderError, match="stale"):
        fx.ECBReferenceFXProvider().rate("USD", "EUR")
    _patch(monkeypatch, _xml(date.today().isoformat(), {"USD": 1.12}))
    with pytest.raises(GlobalProviderError, match="no reference rate for XYZ"):
        fx.ECBReferenceFXProvider().rate("XYZ", "EUR")


def test_resolve_fx_rates_reports_missing_currency_instead_of_defaulting(monkeypatch):
    from global_markets.service import resolve_fx_rates

    _patch(monkeypatch, _xml(date.today().isoformat(), {"GBP": 0.85, "USD": 1.12}))
    monkeypatch.delenv("BIAP_GLOBAL_MARKET_API_KEY", raising=False)
    rates, errors, sources = resolve_fx_rates(["GBP", "USD", "XYZ"], "EUR")
    assert rates["GBP"] == pytest.approx(1 / 0.85) and rates["USD"] == pytest.approx(1 / 1.12)
    assert "XYZ" not in rates and "no reference rate for XYZ" in errors["XYZ"]
    assert sources["GBP"]["provider"] == "ecb-euro-reference-rates" and sources["GBP"]["rateDate"]
