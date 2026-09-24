from pathlib import Path

def replace_once(path, old, new):
    p=Path(path)
    text=p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}")
    p.write_text(text.replace(old,new,1),encoding="utf-8")

replace_once(
    "analysis/global_markets/esma_firds_universe.py",
    '    ("ES", "BME_MADRID"): "XMAD",\n}',
    '    ("ES", "BME_MADRID"): "XMAD",\n    ("SE", "NASDAQ_STOCKHOLM"): "XSTO",\n    ("DK", "NASDAQ_COPENHAGEN"): "XCSE",\n}'
)

replace_once(
    "analysis/global_markets/runtime.py",
    '    registry.register_universe("ES", "BME_MADRID", firds_eu)\n',
    '    registry.register_universe("ES", "BME_MADRID", firds_eu)\n    registry.register_universe("SE", "NASDAQ_STOCKHOLM", firds_eu)\n    registry.register_universe("DK", "NASDAQ_COPENHAGEN", firds_eu)\n'
)

replace_once(
    "analysis/global_markets/cached_universe.py",
    '# Version 11 invalidates FIRDS snapshots built before the official Euronext\n# regulated-directory resolver was integrated. Membership remains FIRDS-defined;\n# refreshed snapshots resolve local symbols from Euronext first and use OpenFIGI\n# only for exact FIRDS ISINs missing from the official directory.\nCACHE_SCHEMA_VERSION = 11\n',
    '# Version 12 extends authoritative FIRDS membership to Sweden and Denmark.\n# Old vendor/reference snapshots for XSTO/XCSE must not survive this semantic\n# change; all authoritative market caches are rebuilt under the same schema.\nCACHE_SCHEMA_VERSION = 12\n'
)

replace_once(
    "analysis/tests/test_global_universe_cache_v8.py",
    'def test_universe_cache_schema_is_v11():\n    assert CACHE_SCHEMA_VERSION == 11\n',
    'def test_universe_cache_schema_is_v12():\n    assert CACHE_SCHEMA_VERSION == 12\n'
)

Path("analysis/tests/test_global_firds_se_dk.py").write_text("""from global_markets.esma_firds_universe import ESMAFIRDSOpenFIGIUniverseProvider
from global_markets.runtime import build_registry


def test_firds_supports_stockholm_and_copenhagen():
    provider = ESMAFIRDSOpenFIGIUniverseProvider()
    assert provider.supported("SE", "NASDAQ_STOCKHOLM")
    assert provider.supported("DK", "NASDAQ_COPENHAGEN")


def test_runtime_uses_authoritative_firds_for_stockholm_and_copenhagen():
    registry = build_registry()
    for country, exchange in [
        ("SE", "NASDAQ_STOCKHOLM"),
        ("DK", "NASDAQ_COPENHAGEN"),
    ]:
        wrapper = registry.universe(country, exchange)
        upstream = getattr(wrapper, "upstream", wrapper)
        assert getattr(upstream, "provider_id", None) == "official-esma-firds-universe"
""", encoding="utf-8")
