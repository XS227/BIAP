from global_markets.country_packs import get_exchange
from global_markets.universe import TwelveDataUniverseProvider


def test_configured_exchange_rejects_row_without_mic():
    provider = TwelveDataUniverseProvider(api_key="demo")
    item = provider._company_from_row(
        country="IT",
        spec=get_exchange("IT", "EURONEXT_MILAN"),
        row={"symbol":"RACE","name":"Ferrari N.V.","type":"Common Stock","currency":"EUR","mic_code":""},
    )
    assert item is None


def test_mic_scoped_page_wins_over_larger_text_fallback():
    provider = TwelveDataUniverseProvider(api_key="demo")
    calls = []
    def fake_request(params, endpoint="stocks"):
        calls.append(dict(params))
        if params.get("mic_code") == "XMIL":
            return {"data":[{"symbol":"RACE","mic_code":"XMIL"}], "count":1}
        return {"data":[{"symbol":f"X{i}"} for i in range(1000)], "count":1000}
    provider._request = fake_request
    payload = provider._get_page(country="IT", spec=get_exchange("IT","EURONEXT_MILAN"), page=1, outputsize=1000)
    assert payload["count"] == 1
    assert len(calls) == 1
    assert calls[0].get("mic_code") == "XMIL"
