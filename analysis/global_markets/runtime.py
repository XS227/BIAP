"""Runtime provider wiring for BIAP Global.

No credential is committed. A provider is registered only when its required
runtime configuration is present. Missing providers therefore become explicit
`unconfigured` diagnostics and are handled by the Evidence Agent.
"""

from __future__ import annotations

import os

from .country_packs import COUNTRY_PACKS
from .esef import ESEFFundamentalsProvider
from .iran_adapter import IranLegacyProvider
from .opendart import OpenDARTFundamentalsProvider
from .providers import ProviderRegistry
from .sec_edgar import SECEdgarFundamentalsProvider
from .twelve_data import TwelveDataMarketProvider
from .universe import IranUniverseProvider, TwelveDataUniverseProvider


# filings.xbrl.org/ESEF currently provides a common structured path for these
# markets. Germany and Ireland are intentionally not assumed covered here; their
# country packs remain configured but need dedicated OAM/issuer adapters.
_ESEF_COUNTRIES = ("SE", "NO", "DK", "FI", "IS", "NL", "FR", "BE", "PT", "IT", "ES", "GB")


def build_registry() -> ProviderRegistry:
    registry = ProviderRegistry()

    # Iran Global bridge always reuses the existing local TSETMC/CODAL stack.
    iran = IranLegacyProvider()
    iran_universe = IranUniverseProvider()
    for exchange in COUNTRY_PACKS["IR"].exchanges:
        registry.register_universe("IR", exchange.code, iran_universe)
        registry.register_market("IR", exchange.code, iran)
        registry.register_fundamentals("IR", exchange.code, iran)

    # One global market/universe provider can serve configured non-Iran venues
    # when the deployment has a licensed key covering that venue.
    if os.environ.get("BIAP_GLOBAL_MARKET_API_KEY"):
        market = TwelveDataMarketProvider()
        universe = TwelveDataUniverseProvider()
        for country, pack in COUNTRY_PACKS.items():
            if country == "IR":
                continue
            for exchange in pack.exchanges:
                registry.register_universe(country, exchange.code, universe)
                registry.register_market(country, exchange.code, market)

    # US official fundamentals via SEC EDGAR/XBRL.
    if os.environ.get("BIAP_SEC_USER_AGENT"):
        sec = SECEdgarFundamentalsProvider()
        for exchange in COUNTRY_PACKS["US"].exchanges:
            registry.register_fundamentals("US", exchange.code, sec)

    # Europe/UK structured annual-report fundamentals via ESEF/UKSEF index.
    esef = ESEFFundamentalsProvider()
    for country in _ESEF_COUNTRIES:
        for exchange in COUNTRY_PACKS[country].exchanges:
            registry.register_fundamentals(country, exchange.code, esef)

    # South Korea official fundamentals via Financial Supervisory Service DART.
    if os.environ.get("BIAP_OPENDART_API_KEY"):
        dart = OpenDARTFundamentalsProvider()
        for exchange in COUNTRY_PACKS["KR"].exchanges:
            registry.register_fundamentals("KR", exchange.code, dart)

    return registry
