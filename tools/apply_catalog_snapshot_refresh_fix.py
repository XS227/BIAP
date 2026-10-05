from pathlib import Path

p = Path('analysis/global_routes.py')
text = p.read_text(encoding='utf-8')
old = '''    total = len(instruments)\n    page = instruments[offset:offset + limit]\n'''
new = '''    # list_instruments() may have created/refreshed the persistent snapshot.\n    # Re-read metadata after that operation so a single API response cannot\n    # simultaneously return official instruments while claiming catalog\n    # availability is false/stale from the pre-refresh state.\n    if hasattr(provider, "snapshot_info"):\n        try:\n            snapshot_info = provider.snapshot_info(country=country.upper(), exchange=spec.code)\n        except Exception:\n            pass\n\n    total = len(instruments)\n    page = instruments[offset:offset + limit]\n'''
if new not in text:
    if old not in text:
        raise SystemExit('global_instruments post-refresh anchor missing')
    text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

Path('analysis/tests/test_global_catalog_snapshot_refresh.py').write_text(r'''from global_markets.models import GlobalCompany
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
''', encoding='utf-8')
