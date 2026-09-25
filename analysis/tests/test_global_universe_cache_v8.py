import json
from pathlib import Path

from global_markets.cached_universe import CACHE_SCHEMA_VERSION, PersistentUniverseProvider
from global_markets.models import GlobalCompany
from global_markets.providers import InstrumentUniverseProvider


class EmptyUniverse(InstrumentUniverseProvider):
    provider_id = "empty"
    def list_instruments(self, *, country=None, exchange=None):
        return []


def test_universe_cache_schema_is_v23():
    assert CACHE_SCHEMA_VERSION == 23


def test_v7_cache_is_invalidated(tmp_path: Path):
    provider = PersistentUniverseProvider(EmptyUniverse(), data_dir=str(tmp_path), fresh_hours=12)
    path = tmp_path / "universe" / "IT" / "EURONEXT_MILAN.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schemaVersion": 7,
        "country": "IT",
        "exchange": "EURONEXT_MILAN",
        "provider": "legacy",
        "fetchedAt": "2026-09-23T00:00:00+00:00",
        "instruments": [],
    }), encoding="utf-8")
    assert provider.snapshot_info(country="IT", exchange="EURONEXT_MILAN")["available"] is False


def test_cached_exchange_row_without_mic_is_rejected(tmp_path: Path):
    class BadCacheSource(InstrumentUniverseProvider):
        provider_id = "bad-cache-source"
        def list_instruments(self, *, country=None, exchange=None):
            return [GlobalCompany(
                country="IT", exchange="EURONEXT_MILAN", currency="EUR",
                ticker="RACE", name="Ferrari N.V.", mic_code=None, instrument_type="Common Stock"
            )]
    provider = PersistentUniverseProvider(BadCacheSource(), data_dir=str(tmp_path), fresh_hours=12)
    rows = list(provider.refresh(country="IT", exchange="EURONEXT_MILAN"))
    assert rows == []


def test_trusted_official_jpx_equity_is_not_rejected_for_company_name_note(tmp_path: Path):
    class TrustedJPXSource(InstrumentUniverseProvider):
        provider_id = "official-jpx-test"
        def list_instruments(self, *, country=None, exchange=None):
            return [GlobalCompany(
                country="JP", exchange="TSE_JP", currency="JPY",
                ticker="5243", name="note inc.", mic_code="XJPX",
                instrument_type="Common Stock",
                raw_provider_fields={
                    "official_universe": True,
                    "trusted_official_equity": True,
                },
            )]

    provider = PersistentUniverseProvider(
        TrustedJPXSource(), data_dir=str(tmp_path), fresh_hours=12
    )
    rows = list(provider.refresh(country="JP", exchange="TSE_JP"))
    assert len(rows) == 1
    assert rows[0].ticker == "5243"
    assert rows[0].name == "note inc."


def test_untrusted_note_name_remains_rejected(tmp_path: Path):
    class UntrustedSource(InstrumentUniverseProvider):
        provider_id = "reference-test"
        def list_instruments(self, *, country=None, exchange=None):
            return [GlobalCompany(
                country="JP", exchange="TSE_JP", currency="JPY",
                ticker="5243", name="note inc.", mic_code="XJPX",
                instrument_type="Common Stock",
            )]

    provider = PersistentUniverseProvider(
        UntrustedSource(), data_dir=str(tmp_path), fresh_hours=12
    )
    rows = list(provider.refresh(country="JP", exchange="TSE_JP"))
    assert rows == []
