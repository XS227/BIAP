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
from .cached_fundamentals import PersistentFundamentalsProvider
from .cached_market import PersistentMarketProvider
from .cached_sec_edgar import CachedSECEdgarFundamentalsProvider
from .cached_universe import PersistentUniverseProvider
from .companies_house import CompaniesHouseCorroborator
from .corroboration import CorroboratingFundamentalsProvider
from .country_packs import COUNTRY_PACKS
from .cvm_itr import CVMITRCorroborator
from .cvm_resolver import CVMResolvedFundamentalsProvider
from .edinet import EDINETFundamentalsProvider
from .fallback_fundamentals import FallbackFundamentalsProvider
from .german_issuer import GermanIssuerFundamentalsProvider
from .iran_adapter import IranLegacyProvider
from .kap_current import KAPCurrentFundamentalsProvider
from .opendart import OpenDARTFundamentalsProvider
from .providers import ProviderRegistry
from .regional_yahoo_chart import RegionalYahooChartMarketProvider
from .sec_foreign_ifrs import SECForeignIFRSFundamentalsProvider
from .sgx_issuer import SGXIssuerFundamentalsProvider
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

    # SEC companyfacts is a public, no-key official source. Raw SEC CompanyFacts
    # JSON (including historical facts) is persisted first, then BIAP stores the
    # normalized filing snapshot by filing period. This gives the app both a
    # historical source cache and an outage-safe analysis baseline.
    sec_user_agent = (
        os.environ.get("BIAP_SEC_USER_AGENT")
        or "BIAP Global research application (+https://setai.no)"
    ).strip()
    sec = PersistentFundamentalsProvider(CachedSECEdgarFundamentalsProvider(user_agent=sec_user_agent))
    for exchange in COUNTRY_PACKS["US"].exchanges:
        register_fundamentals("US", exchange.code, sec)

    # Europe: official ESEF first. If an issuer cannot be safely joined to an
    # ESEF filing, use labelled vendor metrics so cards/agents are not empty,
    # while keeping the Evidence gate BLOCKED until official provenance exists.
    # ESEF HTTP responses already have a disk cache; the normalized wrapper adds
    # a stable per-company filing archive and stale-source resilience.
    # UK can additionally corroborate the legal entity against Companies House
    # when its free API credential has been configured.
    esef = CachedESEFFundamentalsProvider()
    sec_foreign_ifrs = SECForeignIFRSFundamentalsProvider(user_agent=sec_user_agent)
    official_europe = FallbackFundamentalsProvider(esef, sec_foreign_ifrs)
    esef_with_fallback = FallbackFundamentalsProvider(official_europe, public_fundamentals)
    esef_persistent = PersistentFundamentalsProvider(esef_with_fallback)

    # Germany keeps generic regulatory ESEF/SEC first. Siemens and Allianz are
    # currently absent from the public ESEF index used by BIAP, so an exact,
    # whitelisted issuer-published annual-results adapter is the next official
    # fallback. It never applies to other German tickers and never upgrades
    # Yahoo/vendor data to official evidence.
    de_issuer = GermanIssuerFundamentalsProvider()
    de_official = FallbackFundamentalsProvider(official_europe, de_issuer)
    de_with_fallback = FallbackFundamentalsProvider(de_official, public_fundamentals)
    de_provider = PersistentFundamentalsProvider(de_with_fallback)
    companies_house_key = (os.environ.get("BIAP_COMPANIES_HOUSE_API_KEY") or "").strip()
    uk_base = (
        CorroboratingFundamentalsProvider(
            esef_with_fallback,
            CompaniesHouseCorroborator(api_key=companies_house_key),
        )
        if companies_house_key
        else esef_with_fallback
    )
    uk_provider = PersistentFundamentalsProvider(uk_base)
    for country in _ESEF_COUNTRIES:
        if country == "GB":
            provider = uk_provider
        elif country == "DE":
            provider = de_provider
        else:
            provider = esef_persistent
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

    # Singapore: keep SGXNet itself out of generic ingestion until its backend
    # access/redistribution path is explicitly approved. For now a strict
    # issuer-owned adapter covers Singapore Exchange Limited (S68) only; every
    # other SG ticker falls back to labelled vendor metrics and remains blocked
    # by Evidence Agent until an official source is added.
    sg_issuer = PersistentFundamentalsProvider(
        FallbackFundamentalsProvider(SGXIssuerFundamentalsProvider(), public_fundamentals)
    )
    for exchange in COUNTRY_PACKS["SG"].exchanges:
        register_fundamentals("SG", exchange.code, sg_issuer)

    # ASX/issuer disclosures are licensing-sensitive. An authorized ingestion
    # job writes normalized verified records to the server filing drop.
    au = VerifiedFilingDropProvider(country="AU", provider_names=("asx", "asx-issuer", "issuer"))
    au_with_fallback = FallbackFundamentalsProvider(au, public_fundamentals)
    for exchange in COUNTRY_PACKS["AU"].exchanges:
        register_fundamentals("AU", exchange.code, au_with_fallback)

    # Brazil: regulator-published CVM DFP is the annual fundamentals base and
    # CVM ITR is an independent official quarterly corroboration stream. The B3
    # display-name resolver still requires one unique CVM CNPJ before evidence
    # can clear; abbreviated share-class labels are never fuzzily matched.
    br_annual = FallbackFundamentalsProvider(CVMResolvedFundamentalsProvider(), public_fundamentals)
    br = CorroboratingFundamentalsProvider(br_annual, CVMITRCorroborator())
    for exchange in COUNTRY_PACKS["BR"].exchanges:
        register_fundamentals("BR", exchange.code, br)

    # Türkiye: KAP is the official Public Disclosure Platform. Its current page
    # contains several comparative annual columns. Persist the normalized result
    # so completed KAP periods remain available locally if the public site is
    # temporarily unavailable.
    tr_base = FallbackFundamentalsProvider(KAPCurrentFundamentalsProvider(), public_fundamentals)
    tr = PersistentFundamentalsProvider(tr_base)
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
