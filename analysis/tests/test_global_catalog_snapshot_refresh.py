from global_markets.models import GlobalCompany
import global_routes


class FakeProvider:
    def __init__(self):
        self.refreshed = False

    def snapshot_info(self, *, country, exchange):
        return {
            "available": self.refreshed,
            "provider": "official-test-universe",
            "officialCount": 1 if self.refreshed else None,
            "resolvedCount": 1 if self.refreshed else None,
        }

    def list_instruments(self, *, country=None, exchange=None):
        self.refreshed = True
        return [GlobalCompany(
            country="NL",
            exchange="EURONEXT_AMSTERDAM",
            currency="EUR",
            ticker="TEST",
            name="Test N.V.",
            mic_code="XAMS",
            isin="NL0000000001",
            instrument_type="Common Stock",
        )]


class FakeRegistry:
    def __init__(self, provider):
        self.provider = provider

    def universe(self, country, exchange):
        return self.provider


def test_instrument_browse_reports_post_refresh_snapshot(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(global_routes, "build_registry", lambda: FakeRegistry(provider))
    result = global_routes.global_instruments(
        "NL", "EURONEXT_AMSTERDAM", q=None, limit=10, offset=0
    )
    assert result["totalMatched"] == 1
    assert result["catalog"]["available"] is True
    assert result["catalog"]["officialCount"] == 1
