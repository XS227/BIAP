"""Runtime provider wiring for BIAP Global.

No credential is committed. Reference-data discovery is available through a
public demo catalog. Verified market snapshots remain usable through the
persistent cache even when the live price/history credential is temporarily
absent. Missing official fundamentals remain explicit to the Evidence Agent;
public vendor financial metrics may supplement the UI/agents but never silently
upgrade themselves to official filing evidence.
"""
from __future__ import annotations

import os

from .cached_esef import CachedESEFFundamentalsProvider
from .cached_market import PersistentMarketProvider
from .cached_universe import PersistentUniverseProvider
from .companies_house import CompaniesHouseCorroborator
from .corroboration import CorroboratingFundamentalsProvider
from .country_packs import COUNTRY_PACKS
from .cvm import CVMFundamentalsProvider
from .cvm_itr import CVMITRCorroborator
from .edinet import EDINETFundamentalsProvider
from .fallback_fundamentals import FallbackFundamentalsProvider
from .iran_adapter import IranLegacyProvider
from .kap import KAPFundamentalsProvider
from .opendart import OpenDARTFundamentalsProvider
from .providers import ProviderRegistry
from .regional_yahoo_chart import RegionalYahooChartMarketProvider
from .sec_edgar import SECEdgarFundamentalsProvider
from .twelve_data import TwelveDataMarketProvider
from .universe import IranUniverseProvider, TwelveDataUniverseProvider
from .verified_filing_drop import VerifiedFilingDropProvider
from .yahoo_fundamentals import YahooFundamentalsProvider

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
    universe = PersistentUniverseProvider(
        TwelveDataUniverseProvider(api_key=os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "demo")
    )
    for country, pack in COUNTRY_PACKS.items():
        if country == "IR":
            continue
        for exchange in pack.exchanges:
            registry.register_universe(country, exchange.code, universe)

    # Licensed Twelve Data remains the preferred market source. Without a
    # licensed credential, BIAP uses a lower-trust public EOD fallback only on
    # venues with deterministic Yahoo symbol suffixes. Every successful result
    # is persisted; ambiguous venues remain cache-only rather than being guessed.
    market_key = (os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "").strip()
    licensed_market = PersistentMarketProvider(TwelveDataMarketProvider()) if market_key else None
    public_market = PersistentMarketProvider(RegionalYahooChartMarketProvider()) if not market_key else None
    cache_only_market = PersistentMarketProvider(None)
    for country, pack in COUNTRY_PACKS.items():
        if country == "IR":
            continue
        for exchange in pack.exchanges:
            if licensed_market is not None:
                provider = licensed_market
            elif public_market is not None and RegionalYahooChartMarketProvider.supported(country, exchange.code):
                provider = public_market
            else:
                provider = cache_only_market
            registry.register_market(country, exchange.code, provider)

    # Public vendor annual financial metrics are a display/analysis supplement,
    # not official filing evidence. Its SourceEvidence type intentionally does
    # not satisfy EvidenceAgent's fundamental_source gate.
    public_fundamentals = YahooFundamentalsProvider()
    fundamentals_registered: set[tuple[str, str]] = set()

    def register_fundamentals(country: str, exchange_code: str, provider) -> None:
        registry.register_fundamentals(country, exchange_code, provider)
        fundamentals_registered.add((country.upper(), exchange_code.upper()))

    # SEC companyfacts is a public, no-key official source. Always register the
    # adapter and use a descriptive project contact URL when deployment has not
    # provided a more specific User-Agent string.
    sec_user_agent = (
        os.environ.get("BIAP_SEC_USER_AGENT")
        or "BIAP Global research application (+https://setai.no)"
    ).strip()
    sec = SECEdgarFundamentalsProvider(user_agent=sec_user_agent)
    for exchange in COUNTRY_PACKS["US"].exchanges:
        register_fundamentals("US", exchange.code, sec)

    # Europe: official ESEF first. If an issuer cannot be safely joined to an
    # ESEF filing, use labelled vendor metrics so cards/agents are not empty,
    # while keeping the Evidence gate BLOCKED until official provenance exists.
    # UK can additionally corroborate the legal entity against Companies House
    # when its free API credential has been configured.
    esef = CachedESEFFundamentalsProvider()
    esef_with_fallback = FallbackFundamentalsProvider(esef, public_fundamentals)
    companies_house_key = (os.environ.get("BIAP_COMPANIES_HOUSE_API_KEY") or "").strip()
    uk_provider = (
        CorroboratingFundamentalsProvider(
            esef_with_fallback,
            CompaniesHouseCorroborator(api_key=companies_house_key),
        )
        if companies_house_key
        else esef_with_fallback
    )
    for country in _ESEF_COUNTRIES:
        provider = uk_provider if country == "GB" else esef_with_fallback
        for exchange in COUNTRY_PACKS[country].exchanges:
            register_fundamentals(country, exchange.code, provider)

    # Japan: EDINET remains authoritative when its deployment key is available.
    if os.environ.get("BIAP_EDINET_API_KEY"):
        edinet = EDINETFundamentalsProvider()
        jp_provider = FallbackFundamentalsProvider(edinet, public_fundamentals)
    else:
        jp_provider = public_fundamentals
    for exchange in COUNTRY_PACKS["JP"].exchanges:
        register_fundamentals("JP", exchange.code, jp_provider)

    if os.environ.get("BIAP_OPENDART_API_KEY"):
        dart = OpenDARTFundamentalsProvider()
        for exchange in COUNTRY_PACKS["KR"].exchanges:
            register_fundamentals("KR", exchange.code, dart)

    # ASX/issuer disclosures are licensing-sensitive. An authorized ingestion
    # job writes normalized verified records to the server filing drop.
    au = VerifiedFilingDropProvider(country="AU", provider_names=("asx", "asx-issuer", "issuer"))
    au_with_fallback = FallbackFundamentalsProvider(au, public_fundamentals)
    for exchange in COUNTRY_PACKS["AU"].exchanges:
        register_fundamentals("AU", exchange.code, au_with_fallback)

    # Brazil: regulator-published CVM DFP is the annual fundamentals base and
    # CVM ITR is an independent official quarterly corroboration stream.
    br_annual = FallbackFundamentalsProvider(CVMFundamentalsProvider(), public_fundamentals)
    br = CorroboratingFundamentalsProvider(br_annual, CVMITRCorroborator())
    for exchange in COUNTRY_PACKS["BR"].exchanges:
        register_fundamentals("BR", exchange.code, br)

    # Türkiye: KAP is the official Public Disclosure Platform. Its public BIST
    # directory and financial-summary pages expose selected annual statement
    # lines without an API credential. Use the latest completed annual column as
    # official evidence and fall back to vendor metrics only if KAP is unavailable.
    tr = FallbackFundamentalsProvider(KAPFundamentalsProvider(), public_fundamentals)
    for exchange in COUNTRY_PACKS["TR"].exchanges:
        register_fundamentals("TR", exchange.code, tr)

    # Other deterministic Yahoo-routed markets currently lack a complete
    # official filing adapter in this branch. Give those markets useful public
    # financial metrics now, but deliberately leave recommendation verification
    # blocked until their official source adapter is connected.
    for country, pack in COUNTRY_PACKS.items():
        if country == "IR":
            continue
        for exchange in pack.exchanges:
            key = (country.upper(), exchange.code.upper())
            if key in fundamentals_registered:
                continue
            if RegionalYahooChartMarketProvider.supported(country, exchange.code):
                register_fundamentals(country, exchange.code, public_fundamentals)

    return registry
