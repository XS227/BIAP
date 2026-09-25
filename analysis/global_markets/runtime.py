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

from .adx_fundamentals import ADXFinancialSummaryProvider
from .adx_market import ADXOfficialMarketProvider
from .adx_official import ADXOfficialUniverseProvider
from .b3_official import B3OfficialUniverseProvider
from .bist_official import BISTOfficialUniverseProvider
from .bse_official import BSEOfficialUniverseProvider
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
from .dfm_fundamentals import DFMEfsahAnnualFundamentalsProvider
from .dfm_market import DFMOfficialMarketProvider
from .dfm_official import DFMOfficialUniverseProvider
from .edinet import EDINETFundamentalsProvider
from .esma_firds_universe import ESMAFIRDSOpenFIGIUniverseProvider
from .euronext_live import EuronextRegulatedUniverseProvider
from .nasdaq_nordic import NasdaqNordicUniverseProvider
from .nzx_official import NZXOfficialUniverseProvider
from .nzx_issuer import NZXIssuerFundamentalsProvider
from .fallback_fundamentals import FallbackFundamentalsProvider
from .german_issuer import GermanIssuerFundamentalsProvider
from .hkex_issuer import HKEXIssuerFundamentalsProvider
from .hkex_official import HKEXOfficialUniverseProvider
from .india_official import NSEOfficialUniverseProvider
from .iran_adapter import IranLegacyProvider
from .jpx_official import JPXOfficialUniverseProvider
from .jse_official import JSEOfficialUniverseProvider
from .krx_official import KRXKINDOfficialUniverseProvider
from .kap_current import KAPCurrentFundamentalsProvider
from .lse_official import LSEOfficialUniverseProvider
from .opendart import OpenDARTFundamentalsProvider
from .official_universe import ASXUniverseProvider, DeutscheBoerseUniverseProvider
from .providers import ProviderRegistry
from .regional_yahoo_chart import RegionalYahooChartMarketProvider
from .sec_foreign_ifrs import SECForeignIFRSFundamentalsProvider
from .sec_crosslisted_gaap import SECCrossListedUSGAAPFundamentalsProvider
from .sgx_issuer import SGXIssuerFundamentalsProvider
from .sgx_official import SGXOfficialUniverseProvider
from .saudi_official import SaudiExchangeOfficialUniverseProvider
from .six_official import SIXOfficialUniverseProvider
from .swiss_issuer import SwissIssuerFundamentalsProvider
from .twelve_data import TwelveDataMarketProvider
from .tsx_official import TMXOfficialUniverseProvider
from .universe import IranUniverseProvider, TwelveDataUniverseProvider
from .us_official import NasdaqTraderUSUniverseProvider
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

    # Reference catalog remains useful for search/discovery on markets where an
    # official listing source has not yet been integrated. It is never enough,
    # by itself, to make a market ranking authoritative.
    reference_universe = PersistentUniverseProvider(
        TwelveDataUniverseProvider(api_key=os.environ.get("BIAP_GLOBAL_MARKET_API_KEY") or "demo")
    )
    for country, pack in COUNTRY_PACKS.items():
        if country == "IR":
            continue
        for exchange in pack.exchanges:
            registry.register_universe(country, exchange.code, reference_universe)

    # Authoritative listing universes override the vendor reference catalog.
    # Deutsche Boerse publishes current T7 instrument reference files for Xetra
    # and Frankfurt. ASX publishes the complete listed-company ISIN directory.
    de_universe = PersistentUniverseProvider(DeutscheBoerseUniverseProvider())
    registry.register_universe("DE", "XETRA", de_universe)
    registry.register_universe("DE", "FRANKFURT", de_universe)

    asx_universe = PersistentUniverseProvider(ASXUniverseProvider())
    registry.register_universe("AU", "ASX", asx_universe)

    jpx_universe = PersistentUniverseProvider(
        JPXOfficialUniverseProvider(),
        fresh_hours=24,
    )
    registry.register_universe("JP", "TSE_JP", jpx_universe)

    b3_universe = PersistentUniverseProvider(
        B3OfficialUniverseProvider(),
        fresh_hours=24,
    )
    registry.register_universe("BR", "B3", b3_universe)

    bist_universe = PersistentUniverseProvider(
        BISTOfficialUniverseProvider(),
        fresh_hours=24,
    )
    registry.register_universe("TR", "BIST", bist_universe)

    us_universe = PersistentUniverseProvider(
        NasdaqTraderUSUniverseProvider(),
        fresh_hours=6,
    )
    registry.register_universe("US", "NASDAQ", us_universe)
    registry.register_universe("US", "NYSE", us_universe)

    tmx_universe = PersistentUniverseProvider(
        TMXOfficialUniverseProvider(),
        fresh_hours=24,
    )
    registry.register_universe("CA", "TSX", tmx_universe)
    registry.register_universe("CA", "TSXV", tmx_universe)

    nse_universe = PersistentUniverseProvider(
        NSEOfficialUniverseProvider(),
        fresh_hours=24,
    )
    registry.register_universe("IN", "NSE", nse_universe)

    bse_universe = PersistentUniverseProvider(
        BSEOfficialUniverseProvider(),
        fresh_hours=12,
    )
    registry.register_universe("IN", "BSE", bse_universe)

    krx_universe = PersistentUniverseProvider(
        KRXKINDOfficialUniverseProvider(),
        fresh_hours=12,
    )
    registry.register_universe("KR", "KRX", krx_universe)

    hkex_universe = PersistentUniverseProvider(
        HKEXOfficialUniverseProvider(),
        fresh_hours=12,
    )
    registry.register_universe("HK", "HKEX", hkex_universe)

    jse_universe = PersistentUniverseProvider(
        JSEOfficialUniverseProvider(),
        fresh_hours=24,
    )
    registry.register_universe("ZA", "JSE", jse_universe)

    six_universe = PersistentUniverseProvider(
        SIXOfficialUniverseProvider(),
        fresh_hours=12,
    )
    registry.register_universe("CH", "SIX", six_universe)

    nzx_universe = PersistentUniverseProvider(
        NZXOfficialUniverseProvider(),
        fresh_hours=24,
    )
    registry.register_universe("NZ", "NZX", nzx_universe)

    sgx_universe = PersistentUniverseProvider(
        SGXOfficialUniverseProvider(),
        fresh_hours=12,
    )
    registry.register_universe("SG", "SGX", sgx_universe)

    dfm_universe = PersistentUniverseProvider(
        DFMOfficialUniverseProvider(),
        fresh_hours=12,
    )
    adx_universe = PersistentUniverseProvider(
        ADXOfficialUniverseProvider(),
        fresh_hours=12,
    )
    registry.register_universe("AE", "ADX", adx_universe)

    registry.register_universe("AE", "DFM", dfm_universe)

    saudi_universe = PersistentUniverseProvider(
        SaudiExchangeOfficialUniverseProvider(),
        fresh_hours=12,
    )
    registry.register_universe("SA", "SAUDI_EXCHANGE", saudi_universe)

    # France and Italy: ESMA FIRDS is the authoritative regulated/native common-
    # share membership source. OpenFIGI is used only to resolve the local ticker.
    # Cache for one FIRDS full-file cycle so an app request never has to resolve
    # hundreds of ISINs synchronously under the unauthenticated OpenFIGI limit.
    firds_eu = PersistentUniverseProvider(
        ESMAFIRDSOpenFIGIUniverseProvider(),
        fresh_hours=168,
    )
    registry.register_universe("FR", "EURONEXT_PARIS", firds_eu)
    registry.register_universe("IT", "EURONEXT_MILAN", firds_eu)
    registry.register_universe("NL", "EURONEXT_AMSTERDAM", firds_eu)
    registry.register_universe("BE", "EURONEXT_BRUSSELS", firds_eu)
    registry.register_universe("PT", "EURONEXT_LISBON", firds_eu)
    registry.register_universe("NO", "EURONEXT_OSLO", firds_eu)
    registry.register_universe("ES", "BME_MADRID", firds_eu)

    nasdaq_nordic = PersistentUniverseProvider(
        NasdaqNordicUniverseProvider(),
        fresh_hours=12,
    )
    for country, exchange in (
        ("SE", "NASDAQ_STOCKHOLM"),
        ("DK", "NASDAQ_COPENHAGEN"),
        ("FI", "NASDAQ_HELSINKI"),
        ("IS", "NASDAQ_ICELAND"),
    ):
        registry.register_universe(country, exchange, nasdaq_nordic)

    dublin_universe = PersistentUniverseProvider(
        EuronextRegulatedUniverseProvider(),
        fresh_hours=12,
    )
    registry.register_universe("IE", "EURONEXT_DUBLIN", dublin_universe)

    lse_universe = PersistentUniverseProvider(
        LSEOfficialUniverseProvider(),
        fresh_hours=12,
    )
    registry.register_universe("GB", "LSE", lse_universe)

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

    # DFM publishes its own current quote and exchange-rendered close history.
    # Prefer this official public market source over licensed/vendor/cache-only
    # routing so price provenance can satisfy the Evidence Agent without a key.
    registry.register_market(
        "AE",
        "DFM",
        PersistentMarketProvider(DFMOfficialMarketProvider(), fresh_hours=1),
    )
    registry.register_market(
        "AE",
        "ADX",
        PersistentMarketProvider(ADXOfficialMarketProvider(), fresh_hours=1),
    )

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
    de_drop = VerifiedFilingDropProvider(
        country="DE",
        provider_names=(GermanIssuerFundamentalsProvider.provider_id,),
    )
    de_issuer_resilient = FallbackFundamentalsProvider(de_issuer, de_drop)
    de_official = FallbackFundamentalsProvider(official_europe, de_issuer_resilient)
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

    # Canada: many exact TSX/TSXV issuer identities are also SEC foreign
    # private issuers filing audited IFRS annual data on Form 40-F. Use SEC
    # CompanyFacts only when ticker resolution and legal-name identity both
    # verify; all other Canadian issuers fall back to labelled vendor display
    # metrics and remain Evidence-BLOCKED. Canadian 40-F coverage is issuer-specific.
    ca_sec_official = FallbackFundamentalsProvider(
        SECForeignIFRSFundamentalsProvider(user_agent=sec_user_agent),
        SECCrossListedUSGAAPFundamentalsProvider(user_agent=sec_user_agent),
    )
    ca_sec_ifrs = PersistentFundamentalsProvider(
        FallbackFundamentalsProvider(
            ca_sec_official,
            public_fundamentals,
        )
    )
    for exchange in COUNTRY_PACKS["CA"].exchanges:
        register_fundamentals("CA", exchange.code, ca_sec_ifrs)

    # South Africa: exact JSE issuers that also file audited IFRS annual
    # statements with the SEC can use the same strict foreign-issuer CompanyFacts
    # path. Ticker and legal-name identity must both verify; unsupported JSE
    # issuers remain vendor-display-only and Evidence-BLOCKED.
    za_sec = PersistentFundamentalsProvider(
        FallbackFundamentalsProvider(
            SECForeignIFRSFundamentalsProvider(user_agent=sec_user_agent),
            public_fundamentals,
        )
    )
    register_fundamentals("ZA", "JSE", za_sec)

    # Singapore: keep SGXNet itself out of generic ingestion until its backend
    # access/redistribution path is explicitly approved. For now a strict
    # issuer-owned adapter covers Singapore Exchange Limited (S68) only; every
    # other SG ticker falls back to labelled vendor metrics and remains blocked
    # by Evidence Agent until an official source is added.
    sg_drop = VerifiedFilingDropProvider(
        country="SG",
        provider_names=(SGXIssuerFundamentalsProvider.provider_id,),
    )
    sg_official = FallbackFundamentalsProvider(SGXIssuerFundamentalsProvider(), sg_drop)
    sg_issuer = PersistentFundamentalsProvider(
        FallbackFundamentalsProvider(sg_official, public_fundamentals)
    )
    for exchange in COUNTRY_PACKS["SG"].exchanges:
        register_fundamentals("SG", exchange.code, sg_issuer)

    # Hong Kong: generic HKEXnews ingestion remains separate. For HKEX itself
    # (0388/388), use its issuer-published consolidated annual statements from
    # the official HKEX Group Investor Relations site. Other HK tickers remain
    # on labelled vendor fundamentals and therefore stay Evidence-BLOCKED.
    hk_drop = VerifiedFilingDropProvider(
        country="HK",
        provider_names=(HKEXIssuerFundamentalsProvider.provider_id,),
    )
    hk_official = FallbackFundamentalsProvider(HKEXIssuerFundamentalsProvider(), hk_drop)
    hk_issuer = PersistentFundamentalsProvider(
        FallbackFundamentalsProvider(hk_official, public_fundamentals)
    )
    for exchange in COUNTRY_PACKS["HK"].exchanges:
        register_fundamentals("HK", exchange.code, hk_issuer)

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

    # ADX exposes issuer-filed annual Financial Reports through its official efid
    # disclosures feed. The adapter verifies the linked PDF and cross-checks
    # overlapping headline metrics against ADX's structured annual summary.
    ae_adx = PersistentFundamentalsProvider(
        FallbackFundamentalsProvider(ADXFinancialSummaryProvider(), public_fundamentals)
    )
    register_fundamentals("AE", "ADX", ae_adx)

    # DFM Efsah exposes the issuer-filed annual statement PDF itself. BIAP
    # selects the latest completed yearly filing and extracts only verified
    # headline fields from the primary statements. If a particular issuer PDF
    # cannot be parsed safely, vendor metrics remain display-only fallback and
    # the Evidence gate stays blocked for that issuer.
    ae_dfm = PersistentFundamentalsProvider(
        FallbackFundamentalsProvider(DFMEfsahAnnualFundamentalsProvider(), public_fundamentals)
    )
    register_fundamentals("AE", "DFM", ae_dfm)

    # Switzerland: issuer-owned audited IFRS statements for Nestlé (NESN).
    # Other SIX issuers remain vendor-display-only until a verified primary
    # statement adapter is added for them.
    ch_official = FallbackFundamentalsProvider(
        SwissIssuerFundamentalsProvider(),
        SECForeignIFRSFundamentalsProvider(user_agent=sec_user_agent),
    )
    ch_issuer = PersistentFundamentalsProvider(
        FallbackFundamentalsProvider(ch_official, public_fundamentals)
    )
    register_fundamentals("CH", "SIX", ch_issuer)

    # New Zealand: start with NZX Limited itself using the audited annual
    # report published through NZX's official announcement service. Other NZX
    # issuers remain vendor-display-only until their primary statement parser is
    # verified against issuer-specific annual reports.
    nz_issuer = PersistentFundamentalsProvider(
        FallbackFundamentalsProvider(NZXIssuerFundamentalsProvider(), public_fundamentals)
    )
    register_fundamentals("NZ", "NZX", nz_issuer)

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
