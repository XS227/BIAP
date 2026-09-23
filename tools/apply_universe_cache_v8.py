from pathlib import Path

p = Path('analysis/global_markets/cached_universe.py')
text = p.read_text(encoding='utf-8')
text = text.replace(
    '# Version 6 also invalidates snapshots that could contain structured products\n# misclassified by upstream reference catalogs as Common Stock. Fresh snapshots\n# contain only supported ordinary operating-company equities.\nCACHE_SCHEMA_VERSION = 7\n',
    '# Version 8 invalidates pre-strict-MIC snapshots. Earlier caches could contain\n# instruments whose exchange membership was inferred from a broad country/text\n# query instead of being proven by an accepted venue MIC.\nCACHE_SCHEMA_VERSION = 8\n',
    1,
)
if 'CACHE_SCHEMA_VERSION = 8' not in text:
    raise SystemExit('cache schema anchor not found')

old = '''            if not _ordinary_equity_row(\n                country=row_country,\n                spec=spec,\n                row=normalized_row,\n                symbol=ticker,\n                currency=currency,\n            ):\n                continue\n'''
new = '''            if not _ordinary_equity_row(\n                country=row_country,\n                spec=spec,\n                row=normalized_row,\n                symbol=ticker,\n                currency=currency,\n            ):\n                continue\n            # Cached venue membership must be just as strict as live discovery.\n            # A configured exchange is not trusted unless its cached MIC proves\n            # membership in that venue's accepted MIC set.\n            cached_mic = str(row.get("mic_code") or "").strip().upper()\n            accepted_mics = set(spec.accepted_mics)\n            if accepted_mics and (not cached_mic or cached_mic not in accepted_mics):\n                continue\n'''
if new not in text:
    if old not in text:
        raise SystemExit('cached MIC validation anchor not found')
    text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

p = Path('analysis/tests/test_global_universe_cache_v8.py')
p.write_text('''import json\nfrom pathlib import Path\n\nfrom global_markets.cached_universe import CACHE_SCHEMA_VERSION, PersistentUniverseProvider\nfrom global_markets.models import GlobalCompany\nfrom global_markets.providers import InstrumentUniverseProvider\n\n\nclass EmptyUniverse(InstrumentUniverseProvider):\n    provider_id = "empty"\n    def list_instruments(self, *, country=None, exchange=None):\n        return []\n\n\ndef test_universe_cache_schema_is_v8():\n    assert CACHE_SCHEMA_VERSION == 8\n\n\ndef test_v7_cache_is_invalidated(tmp_path: Path):\n    provider = PersistentUniverseProvider(EmptyUniverse(), data_dir=str(tmp_path), fresh_hours=12)\n    path = tmp_path / "universe" / "IT" / "EURONEXT_MILAN.json"\n    path.parent.mkdir(parents=True, exist_ok=True)\n    path.write_text(json.dumps({\n        "schemaVersion": 7,\n        "country": "IT",\n        "exchange": "EURONEXT_MILAN",\n        "provider": "legacy",\n        "fetchedAt": "2026-09-23T00:00:00+00:00",\n        "instruments": [],\n    }), encoding="utf-8")\n    assert provider.snapshot_info(country="IT", exchange="EURONEXT_MILAN")["available"] is False\n\n\ndef test_cached_exchange_row_without_mic_is_rejected(tmp_path: Path):\n    class BadCacheSource(InstrumentUniverseProvider):\n        provider_id = "bad-cache-source"\n        def list_instruments(self, *, country=None, exchange=None):\n            return [GlobalCompany(\n                country="IT", exchange="EURONEXT_MILAN", currency="EUR",\n                ticker="RACE", name="Ferrari N.V.", mic_code=None, instrument_type="Common Stock"\n            )]\n    provider = PersistentUniverseProvider(BadCacheSource(), data_dir=str(tmp_path), fresh_hours=12)\n    rows = list(provider.refresh(country="IT", exchange="EURONEXT_MILAN"))\n    assert rows == []\n''', encoding='utf-8')
