"""Runtime provider wiring for BIAP Global.

No credential is committed. Reference-data discovery is available through a
public demo catalog. Verified market snapshots remain usable through the
persistent cache even when the live price/history credential is temporarily
absent. Missing market/fundamental providers remain explicit diagnostics and are
handled by the Evidence Agent rather than being fabricated.
"""
from __future__ import annotations

import os

from .cached_esef import CachedESEFFundamentalsProvider
from .cached_market import PersistentMarketProvider
from .cached_universe import PersistentUniverseProvider
from .country_packs import COUNTRY_PACKS
from .edinet import EDINETFundamentalsProvider
from .iran_adapter import IranLegacyProvider
from .opendart import OpenDARTFundamentalsProvider
from .providers import ProviderRegistry
from .sec_edgar import SECEdgarFundamentalsProvider
from .twelve_data import TwelveDataMarketProvider
from .universe import IranUniverseProvider, TwelveDataUniverseProvider
from .verified_filing_drop import VerifiedFilingDropProvider

_ESEF_COUNTRIES = (
    "SE", "NO", "DK", "FI", "IS", "NL", "FR", "BE", "IE", "PT", "IT", "DE", "ES", "GB",
)


def build_registry() -> ProviderRegistry:
    registry = ProviderRegistry()

    iran = IranLegacyProvider()
    iran_universe = PersistentUniverseProvider(IranUniverseProvider())
    for exchange in COUNTRY_PACKS["IR"].exchanges:
        registry.register_universe("IR", exchange.code, iran_universe)
        registry.register_market("IR", exchange.code, iran)
        registry.register_fundamentals("IR", exchange.code, iran)

    # Reference catalog is safe to register independently from the price feed.
    # With no private key, TwelveDataUniverseProvider uses the documented demo
    # authentication only for /stocks metadata. PersistentUniverseProvider keeps
    # the last verified exchange snapshot on the Global server, so temporary
    # upstream failures do not erase the user's ability to browse instruments.
    universe = PersistentUniverseProvider(
        TwelveDataUniverseProvider(api_key=os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "demo")
    )
    for country, pack in COUNTRY_PACKS.items():
        if country == "IR":
            continue
        for exchange in pack.exchanges:
            registry.register_universe(country, exchange.code, universe)

    # A cache-backed market provider is always registered. With a credential it
    # refreshes from Twelve Data and persists verified snapshots; without a
    # credential it becomes read-only cache mode. Missing snapshots still fail
    # explicitly and cannot create synthetic prices.
    market_key = (os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "").strip()
    market = PersistentMarketProvider(TwelveDataMarketProvider() if market_key else None)
    for country, pack in COUNTRY_PACKS.items():
        if country == "IR":
            continue
        for exchange in pack.exchanges:
            registry.register_market(country, exchange.code, market)

    if os.environ.get("BIAP_SEC_USER_AGENT"):
        sec = SECEdgarFundamentalsProvider()
        for exchange in COUNTRY_PACKS["US"].exchanges:
            registry.register_fundamentals("US", exchange.code, sec)

    esef = CachedESEFFundamentalsProvider()
    for country in _ESEF_COUNTRIES:
        for exchange in COUNTRY_PACKS[country].exchanges:
            registry.register_fundamentals(country, exchange.code, esef)

    if os.environ.get("BIAP_EDINET_API_KEY"):
        edinet = EDINETFundamentalsProvider()
        for exchange in COUNTRY_PACKS["JP"].exchanges:
            registry.register_fundamentals("JP", exchange.code, edinet)

    if os.environ.get("BIAP_OPENDART_API_KEY"):
        dart = OpenDARTFundamentalsProvider()
        for exchange in COUNTRY_PACKS["KR"].exchanges:
            registry.register_fundamentals("KR", exchange.code, dart)

    # ASX/issuer disclosures are licensing-sensitive. An authorized ingestion
    # job writes normalized verified records to the server filing drop; this
    # provider refuses anything without explicit provenance and verification.
    au = VerifiedFilingDropProvider(country="AU", provider_names=("asx", "asx-issuer", "issuer"))
    for exchange in COUNTRY_PACKS["AU"].exchanges:
        registry.register_fundamentals("AU", exchange.code, au)

    return registry
