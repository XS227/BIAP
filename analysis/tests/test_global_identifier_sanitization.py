from global_markets.universe import TwelveDataUniverseProvider
from global_routes import InstrumentRequest, _seed


def test_universe_drops_entitlement_sentinel_isin(monkeypatch):
    provider = TwelveDataUniverseProvider(api_key="demo", max_rows=10)

    def fake_page(**_kwargs):
        return {
            "count": 1,
            "data": [
                {
                    "symbol": "EQNR",
                    "name": "Equinor ASA",
                    "mic_code": "XOSL",
                    "currency": "NOK",
                    "type": "Common Stock",
                    "isin": "REQUEST_ACCESS_VIA_ADD_ONS",
                }
            ],
        }

    monkeypatch.setattr(provider, "_get_page", fake_page)
    rows = list(provider.list_instruments(country="NO", exchange="EURONEXT_OSLO"))
    assert len(rows) == 1
    assert rows[0].ticker == "EQNR"
    assert rows[0].isin is None


def test_analysis_request_ignores_restricted_cached_isin():
    req = InstrumentRequest(
        country="NO",
        exchange="EURONEXT_OSLO",
        ticker="EQNR",
        name="Equinor ASA",
        currency="NOK",
        isin="REQUEST_ACCESS_VIA_ADD_ONS",
    )
    company = _seed(req)
    assert company.ticker == "EQNR"
    assert company.isin is None
