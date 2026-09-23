from pathlib import Path

p = Path('analysis/global_markets/cached_universe.py')
text = p.read_text(encoding='utf-8')
old = '''# Version 10 invalidates pre-FIRDS France/Italy snapshots. Those older caches\n# could be MIC-correct yet still include secondary/cross-listed lines. Current\n# official-market caches preserve authoritative membership and resolver coverage.\nCACHE_SCHEMA_VERSION = 10\n'''
new = '''# Version 11 invalidates FIRDS snapshots built before the official Euronext\n# regulated-directory resolver was integrated. Membership remains FIRDS-defined;\n# refreshed snapshots resolve local symbols from Euronext first and use OpenFIGI\n# only for exact FIRDS ISINs missing from the official directory.\nCACHE_SCHEMA_VERSION = 11\n'''
if new not in text:
    if old not in text:
        raise SystemExit('cache v10 anchor missing')
    text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

# Keep the older cache-migration regression aligned with the current schema.
p = Path('analysis/tests/test_global_universe_cache_v8.py')
text = p.read_text(encoding='utf-8')
old = '''def test_universe_cache_schema_is_v10():\n    assert CACHE_SCHEMA_VERSION == 10\n'''
new = '''def test_universe_cache_schema_is_v11():\n    assert CACHE_SCHEMA_VERSION == 11\n'''
if new not in text:
    if old not in text:
        raise SystemExit('legacy cache-schema regression anchor missing')
    text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

# Regression: the migration must remain explicit.
t = Path('analysis/tests/test_global_universe_cache_schema.py')
t.write_text('''from global_markets.cached_universe import CACHE_SCHEMA_VERSION\n\n\ndef test_global_universe_cache_schema_is_euronext_resolver_v11():\n    assert CACHE_SCHEMA_VERSION == 11\n''', encoding='utf-8')
