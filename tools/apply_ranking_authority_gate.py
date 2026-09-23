from pathlib import Path

p=Path('analysis/global_markets/scanner.py')
text=p.read_text(encoding='utf-8')
text=text.replace(
    '        partial_universe: bool,\n        screening_errors: list[str],\n',
    '        partial_universe: bool,\n        screening_errors: list[str],\n        universe_authoritative: bool,\n        universe_source: str,\n',
    1,
)
text=text.replace(
    '        if not live_market_data:\n            reasons.append("full_market_source_unavailable")\n',
    '        if not universe_authoritative:\n            reasons.append("authoritative_universe_unavailable")\n        if not live_market_data:\n            reasons.append("full_market_source_unavailable")\n',
    1,
)
text=text.replace(
    '            "universeSource": "ordinary-equity exchange catalog",\n',
    '            "universeSource": universe_source,\n            "universeAuthoritative": universe_authoritative,\n',
    1,
)
text=text.replace(
    '        if not self.market_api_key:\n',
    '        if not self.market_api_key and self.eodhd_bulk is None:\n',
    1,
)

anchor='''        universe_provider = registry.universe(country, spec.code)\n        universe = list(universe_provider.list_instruments(country=country.upper(), exchange=spec.code))\n'''
replacement='''        universe_provider = registry.universe(country, spec.code)\n        universe_provider_id = str(getattr(universe_provider, "provider_id", "unknown"))\n        authority_allow = {item.strip().upper() for item in (os.environ.get("BIAP_GLOBAL_AUTHORITATIVE_UNIVERSE_MARKETS") or "").split(",") if item.strip()}\n        market_key = f"{country.upper()}:{spec.code.upper()}"\n        # Reference/demo catalogs are useful for search, but cannot prove the\n        # exact regulated/native segment (e.g. XMIL also exposes GEM cross-listings).\n        # Ranking is released only after an authoritative exchange universe is wired\n        # or the specific market has been explicitly validated and allow-listed.\n        universe_authoritative = universe_provider_id.startswith("official-") or market_key in authority_allow\n        universe_source = universe_provider_id\n        universe = list(universe_provider.list_instruments(country=country.upper(), exchange=spec.code))\n'''
if replacement not in text:
    if anchor not in text: raise SystemExit('universe provider anchor missing')
    text=text.replace(anchor,replacement,1)

old='''                market_source="stored market records only", partial_universe=partial, screening_errors=[],\n            )\n'''
new='''                market_source="stored market records only", partial_universe=partial, screening_errors=[],\n                universe_authoritative=universe_authoritative, universe_source=universe_source,\n            )\n'''
if new not in text:
    if old not in text: raise SystemExit('cached readiness anchor missing')
    text=text.replace(old,new,1)

old='''            market_source=market_source, partial_universe=partial, screening_errors=screening_errors,\n        )\n'''
new='''            market_source=market_source, partial_universe=partial, screening_errors=screening_errors,\n            universe_authoritative=universe_authoritative, universe_source=universe_source,\n        )\n'''
if new not in text:
    if old not in text: raise SystemExit('live readiness anchor missing')
    text=text.replace(old,new,1)

p.write_text(text,encoding='utf-8')

p=Path('analysis/tests/test_global_ranking_authority.py')
p.write_text('''from global_markets.scanner import GlobalMarketScanner\n\n\ndef test_readiness_blocks_non_authoritative_universe():\n    scanner=GlobalMarketScanner()\n    result=scanner._readiness(\n        country="IT", exchange="EURONEXT_MILAN", universe_count=200, screened_count=200,\n        deep_results=[], live_market_data=True, market_source="test", partial_universe=False,\n        screening_errors=[], universe_authoritative=False, universe_source="twelve-data-universe-demo",\n    )\n    assert result["rankingEligible"] is False\n    assert "authoritative_universe_unavailable" in result["reasons"]\n    assert result["universeAuthoritative"] is False\n\n\ndef test_eodhd_can_be_full_market_source_without_twelve_key(monkeypatch):\n    monkeypatch.delenv("BIAP_GLOBAL_MARKET_API_KEY", raising=False)\n    monkeypatch.setenv("BIAP_EODHD_API_TOKEN", "token")\n    scanner=GlobalMarketScanner()\n    assert scanner.eodhd_bulk is not None\n''',encoding='utf-8')
