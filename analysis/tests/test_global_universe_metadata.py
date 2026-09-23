from pathlib import Path

from global_markets.cached_universe import PersistentUniverseProvider
from global_markets.models import GlobalCompany
from global_markets.providers import InstrumentUniverseProvider


class PartialOfficialUniverse(InstrumentUniverseProvider):
    provider_id = "official-test-universe"

    def __init__(self):
        self.last_metadata = {}

    def list_instruments(self, *, country=None, exchange=None):
        self.last_metadata = {
            "officialCount": 100,
            "resolvedCount": 95,
            "resolutionCoveragePct": 95.0,
            "publicationDate": "2026-09-19",
        }
        return [
            GlobalCompany(
                country="FR",
                exchange="EURONEXT_PARIS",
                currency="EUR",
                ticker=f"T{i}",
                name=f"Test {i}",
                mic_code="XPAR",
                isin=f"FR{i:010d}"[-12:],
                instrument_type="Common Stock",
            )
            for i in range(95)
        ]


def test_persistent_universe_keeps_official_denominator_metadata(tmp_path: Path):
    provider = PersistentUniverseProvider(PartialOfficialUniverse(), data_dir=str(tmp_path), fresh_hours=12)
    rows = list(provider.refresh(country="FR", exchange="EURONEXT_PARIS"))
    assert len(rows) == 95
    info = provider.snapshot_info(country="FR", exchange="EURONEXT_PARIS")
    assert info["count"] == 95
    assert info["officialCount"] == 100
    assert info["resolvedCount"] == 95
    assert info["resolutionCoveragePct"] == 95.0
    assert info["metadata"]["publicationDate"] == "2026-09-19"
