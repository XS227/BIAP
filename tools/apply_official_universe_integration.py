from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:180]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Runtime: generic vendor catalog remains search/fallback, but exchanges with a
# direct official universe override it before the registry is returned.
replace_once(
    "analysis/global_markets/runtime.py",
    "from .opendart import OpenDARTFundamentalsProvider\n",
    "from .opendart import OpenDARTFundamentalsProvider\nfrom .official_universe import ASXUniverseProvider, DeutscheBoerseUniverseProvider\n",
)

old = '''    # Reference catalog is safe to register independently from the price feed.\n    universe = PersistentUniverseProvider(\n        TwelveDataUniverseProvider(api_key=os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "demo")\n    )\n    for country, pack in COUNTRY_PACKS.items():\n        if country == "IR":\n            continue\n        for exchange in pack.exchanges:\n            registry.register_universe(country, exchange.code, universe)\n'''
new = '''    # Reference catalog remains useful for search/discovery on markets where an\n    # official listing source has not yet been integrated. It is never enough,\n    # by itself, to make a market ranking authoritative.\n    reference_universe = PersistentUniverseProvider(\n        TwelveDataUniverseProvider(api_key=os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "demo")\n    )\n    for country, pack in COUNTRY_PACKS.items():\n        if country == "IR":\n            continue\n        for exchange in pack.exchanges:\n            registry.register_universe(country, exchange.code, reference_universe)\n\n    # Authoritative listing universes override the vendor reference catalog.\n    # Deutsche Boerse publishes current T7 instrument reference files for Xetra\n    # and Frankfurt. ASX publishes the complete listed-company ISIN directory.\n    de_universe = PersistentUniverseProvider(DeutscheBoerseUniverseProvider())\n    registry.register_universe("DE", "XETRA", de_universe)\n    registry.register_universe("DE", "FRANKFURT", de_universe)\n\n    asx_universe = PersistentUniverseProvider(ASXUniverseProvider())\n    registry.register_universe("AU", "ASX", asx_universe)\n'''
replace_once("analysis/global_markets/runtime.py", old, new)

# Scanner: PersistentUniverseProvider prefixes the runtime provider id with
# `cached:`. Authority must be based on its upstream provider identity.
old = '''        universe_provider_id = str(getattr(universe_provider, "provider_id", "unknown"))\n        authority_allow = {item.strip().upper() for item in (os.environ.get("BIAP_GLOBAL_AUTHORITATIVE_UNIVERSE_MARKETS") or "").split(",") if item.strip()}\n        market_key = f"{country.upper()}:{spec.code.upper()}"\n        # Reference/demo catalogs are useful for search, but cannot prove the\n        # exact regulated/native segment (e.g. XMIL also exposes GEM cross-listings).\n        # Ranking is released only after an authoritative exchange universe is wired\n        # or the specific market has been explicitly validated and allow-listed.\n        universe_authoritative = universe_provider_id.startswith("official-") or market_key in authority_allow\n        universe_source = universe_provider_id\n'''
new = '''        universe_provider_id = str(getattr(universe_provider, "provider_id", "unknown"))\n        upstream_universe = getattr(universe_provider, "upstream", universe_provider)\n        authoritative_provider_id = str(getattr(upstream_universe, "provider_id", universe_provider_id))\n        authority_allow = {item.strip().upper() for item in (os.environ.get("BIAP_GLOBAL_AUTHORITATIVE_UNIVERSE_MARKETS") or "").split(",") if item.strip()}\n        market_key = f"{country.upper()}:{spec.code.upper()}"\n        # Reference/demo catalogs are useful for search, but cannot prove the\n        # exact regulated/native segment (e.g. XMIL also exposes GEM cross-listings).\n        # A cached official exchange file remains authoritative because the cache\n        # preserves the upstream identity and freshness metadata.\n        universe_authoritative = authoritative_provider_id.startswith("official-") or market_key in authority_allow\n        universe_source = authoritative_provider_id\n'''
replace_once("analysis/global_markets/scanner.py", old, new)
