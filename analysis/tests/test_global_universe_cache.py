from __future__ import annotations

from pathlib import Path

from global_markets.cached_universe import PersistentUniverseProvider
from global_markets.models import GlobalCompany, SourceEvidence
from global_markets.providers import GlobalProviderError, InstrumentUniverseProvider


class FakeUniverse(InstrumentUniverseProvider):
    provider_id = "fake-universe"

    def __init__(self) -> None:
        self.fail = False
        self.calls = 0

    def list_instruments(self, *, country=None, exchange=None):
        self.calls += 1
        if self.fail:
            raise GlobalProviderError("upstream down")
        return [
            GlobalCompany(
                country=(country or "GB").upper(),
                exchange=(exchange or "LSE").upper(),
                currency="GBP",
                ticker="TEST",
                name="Test plc",
                mic_code="XLON",
                isin="GB0000000001",
                sources=[SourceEvidence(provider=self.provider_id, source_type="instrument_reference", quality=0.9)],
            )
        ]


def test_persistent_universe_writes_and_reuses_fresh_cache(tmp_path: Path):
    upstream = FakeUniverse()
    provider = PersistentUniverseProvider(upstream, data_dir=str(tmp_path), fresh_hours=12)

    first = list(provider.list_instruments(country="GB", exchange="LSE"))
    second = list(provider.list_instruments(country="GB", exchange="LSE"))

    assert first[0].ticker == "TEST"
    assert second[0].ticker == "TEST"
    assert upstream.calls == 1
    assert provider.snapshot_info(country="GB", exchange="LSE")["available"] is True
    assert (tmp_path / "universe" / "GB" / "LSE.json").exists()


def test_persistent_universe_falls_back_to_stale_snapshot(tmp_path: Path):
    upstream = FakeUniverse()
    provider = PersistentUniverseProvider(upstream, data_dir=str(tmp_path), fresh_hours=0)
    list(provider.list_instruments(country="GB", exchange="LSE"))

    upstream.fail = True
    rows = list(provider.list_instruments(country="GB", exchange="LSE"))

    assert rows[0].ticker == "TEST"
    assert rows[0].raw_provider_fields["catalog_cache"] == "fallback"
    cache_sources = [s for s in rows[0].sources if s.source_type == "instrument_reference_cache"]
    assert cache_sources
    assert "fallback snapshot" in (cache_sources[-1].notes or "").lower()


def test_failed_empty_refresh_never_overwrites_good_snapshot(tmp_path: Path):
    upstream = FakeUniverse()
    provider = PersistentUniverseProvider(upstream, data_dir=str(tmp_path), fresh_hours=12)
    list(provider.refresh(country="GB", exchange="LSE"))

    class EmptyUniverse(FakeUniverse):
        def list_instruments(self, *, country=None, exchange=None):
            return []

    empty_provider = PersistentUniverseProvider(EmptyUniverse(), data_dir=str(tmp_path), fresh_hours=0)
    rows = list(empty_provider.list_instruments(country="GB", exchange="LSE"))
    assert rows[0].ticker == "TEST"
