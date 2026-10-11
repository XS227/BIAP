import pytest

from global_markets.cached_fundamentals import PersistentFundamentalsProvider
from global_markets.fallback_fundamentals import FallbackFundamentalsProvider
from global_markets.providers import GlobalProviderError
from global_markets.runtime import build_registry
from global_markets.sec_edgar import SECEdgarFundamentalsProvider
from global_markets.sec_foreign_ifrs import SECForeignIFRSFundamentalsProvider


def test_us_sec_fundamentals_are_registered_without_env(monkeypatch):
    monkeypatch.delenv("BIAP_SEC_USER_AGENT", raising=False)
    registry = build_registry()

    nasdaq = registry.fundamentals("US", "NASDAQ")
    nyse = registry.fundamentals("US", "NYSE")

    assert isinstance(nasdaq, PersistentFundamentalsProvider)
    assert isinstance(nyse, PersistentFundamentalsProvider)
    assert isinstance(nasdaq.upstream, FallbackFundamentalsProvider)
    assert isinstance(nyse.upstream, FallbackFundamentalsProvider)
    from global_markets.us_reviewed_reports import USReviewedSECAnnualReportProvider
    for provider in (nasdaq, nyse):
        chain = provider.upstream
        assert isinstance(chain.fallback, USReviewedSECAnnualReportProvider)
        assert isinstance(chain.primary, FallbackFundamentalsProvider)
        assert chain.primary.primary.user_agent
        assert chain.primary.fallback.user_agent




def test_sec_parser_anchors_to_latest_annual_period_and_drops_stale_revenue(monkeypatch):
    """A stale revenue concept must not make a current 10-K look stale.

    ABSI's 2025 10-K has current balance-sheet/income/cash-flow facts, while the
    generic Revenues concept stops at 2024. The normalized snapshot must anchor
    to 2025 and leave revenue unavailable instead of mixing fiscal periods.
    """
    from global_markets.models import GlobalCompany

    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test contact@example.com")
    seed = GlobalCompany(
        country="US",
        exchange="NASDAQ",
        mic_code="XNAS",
        currency="USD",
        ticker="ABSI",
        name="ABSCI CORP",
    )
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 1672688)

    def row(value, end, filed, *, start=None, unit="USD"):
        result = {
            "val": value,
            "end": end,
            "filed": filed,
            "form": "10-K",
            "fp": "FY",
        }
        if start:
            result["start"] = start
        return result

    payload = {
        "entityName": "ABSCI CORP",
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [
                    row(4_534_000, "2024-12-31", "2025-03-18", start="2024-01-01"),
                ]}},
                "NetIncomeLoss": {"units": {"USD": [
                    row(-115_183_000, "2025-12-31", "2026-03-24", start="2025-01-01"),
                    row(-103_106_000, "2024-12-31", "2026-03-24", start="2024-01-01"),
                ]}},
                "Assets": {"units": {"USD": [
                    row(216_297_000, "2025-12-31", "2026-03-24"),
                ]}},
                "Liabilities": {"units": {"USD": [
                    row(26_848_000, "2025-12-31", "2026-03-24"),
                ]}},
                "StockholdersEquity": {"units": {"USD": [
                    row(189_449_000, "2025-12-31", "2026-03-24"),
                ]}},
                "AssetsCurrent": {"units": {"USD": [
                    row(149_573_000, "2025-12-31", "2026-03-24"),
                ]}},
                "LiabilitiesCurrent": {"units": {"USD": [
                    row(22_765_000, "2025-12-31", "2026-03-24"),
                ]}},
                "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                    row(20_025_000, "2025-12-31", "2026-03-24"),
                ]}},
                "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
                    row(-92_925_000, "2025-12-31", "2026-03-24", start="2025-01-01"),
                ]}},
                "EarningsPerShareDiluted": {"units": {"USD/shares": [
                    row(-0.84, "2025-12-31", "2026-03-24", start="2025-01-01", unit="USD/shares"),
                ]}},
            }
        },
    }
    monkeypatch.setattr(provider, "_get_json", lambda url: payload)

    enriched = provider.enrich_fundamentals(seed)

    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.filing_observed_at == "2026-03-24"
    assert enriched.revenue is None
    assert enriched.revenue_prev is None
    assert enriched.net_income == -115_183_000
    assert enriched.total_assets == 216_297_000
    assert enriched.current_assets == 149_573_000
    assert enriched.eps == -0.84
    assert any(
        source.provider == provider.provider_id
        and source.period_end == "2025-12-31"
        for source in enriched.sources
    )


def test_sec_parser_accepts_audited_fy_facts_from_form_10_registration(monkeypatch):
    from global_markets.models import GlobalCompany

    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test contact@example.com")
    seed = GlobalCompany(
        country="US",
        exchange="NASDAQ",
        mic_code="XNAS",
        currency="USD",
        ticker="WCCB",
        name="West Coast Community Bancorp",
    )
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 2105965)

    def row(value, end="2025-12-31", filed="2026-08-31", *, start=None, fp="FY"):
        out = {"val": value, "end": end, "filed": filed, "form": "10-12B", "fp": fp}
        if start:
            out["start"] = start
        return out

    payload = {
        "entityName": "West Coast Community Bancorp",
        "facts": {"us-gaap": {
            "NetIncomeLoss": {"units": {"USD": [
                row(50_400_000, start="2025-01-01"),
                row(29_600_000, end="2024-12-31", filed="2026-08-31", start="2024-01-01"),
            ]}},
            "Assets": {"units": {"USD": [row(2_700_000_000)]}},
            "Liabilities": {"units": {"USD": [row(2_450_000_000)]}},
            "StockholdersEquity": {"units": {"USD": [row(250_000_000)]}},
            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [row(190_678_000)]}},
        }},
    }
    monkeypatch.setattr(provider, "_get_json", lambda url: payload)

    enriched = provider.enrich_fundamentals(seed)

    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.net_income == 50_400_000
    assert enriched.total_assets == 2_700_000_000
    assert any(source.source_type == "official_regulatory_xbrl" for source in enriched.sources)


def test_sec_parser_accepts_us_gaap_annual_facts_from_form_20f(monkeypatch):
    from global_markets.models import GlobalCompany

    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test contact@example.com")
    seed = GlobalCompany(
        country="US",
        exchange="NASDAQ",
        mic_code="XNAS",
        currency="USD",
        ticker="ODD",
        name="ODDITY TECH LTD.",
    )
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 1907085)

    def row(value, end="2025-12-31", filed="2026-03-17", *, start=None, unit="USD"):
        out = {"val": value, "end": end, "filed": filed, "form": "20-F", "fp": "FY"}
        if start:
            out["start"] = start
        return out

    payload = {
        "entityName": "ODDITY TECH LTD.",
        "facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [
                row(790_000_000, start="2025-01-01"),
                row(650_000_000, end="2024-12-31", filed="2026-03-17", start="2024-01-01"),
            ]}},
            "NetIncomeLoss": {"units": {"USD": [row(120_000_000, start="2025-01-01")]}},
            "Assets": {"units": {"USD": [row(900_000_000)]}},
            "Liabilities": {"units": {"USD": [row(300_000_000)]}},
            "StockholdersEquity": {"units": {"USD": [row(600_000_000)]}},
            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [row(250_000_000)]}},
            "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [row(180_000_000, start="2025-01-01")]}},
        }},
    }
    monkeypatch.setattr(provider, "_get_json", lambda url: payload)

    enriched = provider.enrich_fundamentals(seed)

    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.revenue == 790_000_000
    assert enriched.net_income == 120_000_000
    assert enriched.total_assets == 900_000_000
    assert any(source.source_type == "official_regulatory_xbrl" for source in enriched.sources)


def test_stale_domestic_10k_is_parsed_but_blocked_by_evidence(monkeypatch):
    """Domestic SEC data is not discarded when stale; Evidence must BLOCK it.

    The 10-K provider keeps the latest filed period so the gap stays visible
    (OFFICIAL_STALE) instead of silently falling back to vendor data.
    """
    from datetime import datetime, timezone

    from global_markets.agents import evidence_agent
    from global_markets.evidence_contract import STATUS_OFFICIAL_STALE
    from global_markets.models import GlobalCompany

    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test contact@example.com")
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 1234567)

    def row(value, end, *, start=None):
        result = {"val": value, "end": end, "filed": "2024-03-01", "form": "10-K", "fp": "FY"}
        if start:
            result["start"] = start
        return result

    payload = {"entityName": "STALE FILER INC", "facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [row(50_000_000, "2023-12-31", start="2023-01-01")]}},
        "NetIncomeLoss": {"units": {"USD": [row(4_000_000, "2023-12-31", start="2023-01-01")]}},
        "Assets": {"units": {"USD": [row(90_000_000, "2023-12-31")]}},
        "StockholdersEquity": {"units": {"USD": [row(60_000_000, "2023-12-31")]}},
    }}}
    monkeypatch.setattr(provider, "_get_json", lambda url: payload)
    seed = GlobalCompany(
        country="US", exchange="NASDAQ", mic_code="XNAS", currency="USD",
        ticker="STLE", name="Stale Filer Inc",
    )

    enriched = provider.enrich_fundamentals(seed)
    assert enriched.filing_period_end == "2023-12-31"
    assert enriched.total_liabilities == 30_000_000

    evidence = evidence_agent(enriched, now=datetime(2026, 10, 11, tzinfo=timezone.utc))
    assert evidence.status == "BLOCK"
    assert "fresh_fundamentals" in evidence.missing_critical
    assert "fundamental_source" not in evidence.missing_critical
    assert evidence.official_fundamental_status == STATUS_OFFICIAL_STALE


def _interim_only_successor_payload():
    q2 = {"val": 448_000_000_000, "end": "2026-06-30", "filed": "2026-08-03", "form": "10-Q", "fp": "Q2"}
    return {"entityName": "ExxonMobil Holdings Corp", "facts": {"us-gaap": {
        "Assets": {"units": {"USD": [q2]}},
    }}}


def _xom_seed():
    from global_markets.models import GlobalCompany

    return GlobalCompany(
        country="US", exchange="NYSE", mic_code="XNYS", currency="USD",
        ticker="XOM", name="Exxon Mobil Corporation",
    )


def test_interim_only_sec_filer_is_rejected_not_attached_as_official(monkeypatch):
    """A registrant with only 10-Q facts has no annual official period.

    Attaching an empty SEC source made Evidence report OFFICIAL_CURRENT with
    every fundamental missing (XOM after its 2026 redomiciliation).
    """
    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test contact@example.com")
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 9_999_999)
    monkeypatch.setattr(provider, "_get_json", lambda url: _interim_only_successor_payload())
    with pytest.raises(GlobalProviderError, match="no annual 10-K/20-F period"):
        provider.enrich_fundamentals(_xom_seed())


def test_verified_successor_registrant_reads_predecessor_annual_10k(monkeypatch):
    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test contact@example.com")
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 2115436)

    def fy(value, end="2025-12-31", start=None):
        row = {"val": value, "end": end, "filed": "2026-02-18", "form": "10-K", "fp": "FY"}
        if start:
            row["start"] = start
        return row

    predecessor = {"entityName": "EXXON MOBIL CORP", "facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [fy(330_000_000_000, start="2025-01-01")]}},
        "NetIncomeLoss": {"units": {"USD": [fy(30_000_000_000, start="2025-01-01")]}},
        "Assets": {"units": {"USD": [fy(450_000_000_000)]}},
        "StockholdersEquity": {"units": {"USD": [fy(260_000_000_000)]}},
    }}}
    fetched = []

    def get_json(url):
        fetched.append(url)
        return predecessor if "CIK0000034088" in url else _interim_only_successor_payload()

    monkeypatch.setattr(provider, "_get_json", get_json)
    enriched = provider.enrich_fundamentals(_xom_seed())

    assert enriched.name == "ExxonMobil Holdings Corp"
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.net_income == 30_000_000_000
    assert enriched.raw_provider_fields["sec_cik"] == 2115436
    assert enriched.raw_provider_fields["sec_predecessor_cik"] == 34088
    source = next(s for s in enriched.sources if s.provider == provider.provider_id)
    assert source.source_id == "CIK0000034088"
    assert source.source_url.endswith("CIK0000034088.json")
    assert "predecessor registrant CIK 34088" in source.notes
    assert fetched[0].endswith("CIK0002115436.json")


def test_successor_with_own_annual_facts_does_not_use_predecessor(monkeypatch):
    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test contact@example.com")
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 2115436)
    own = {"entityName": "ExxonMobil Holdings Corp", "facts": {"us-gaap": {
        "NetIncomeLoss": {"units": {"USD": [
            {"val": 31_000_000_000, "end": "2026-12-31", "start": "2026-01-01",
             "filed": "2027-02-17", "form": "10-K", "fp": "FY"},
        ]}},
    }}}
    fetched = []
    monkeypatch.setattr(provider, "_get_json", lambda url: fetched.append(url) or own)
    enriched = provider.enrich_fundamentals(_xom_seed())
    assert enriched.filing_period_end == "2026-12-31"
    assert "sec_predecessor_cik" not in enriched.raw_provider_fields
    assert not any("CIK0000034088" in url for url in fetched)


def test_btbd_same_sec_accession_two_day_fiscal_date_offset(monkeypatch):
    """BTBD FY2024 SEC accession has 12/31 balance sheet and 12/29 P&L."""
    from global_markets.models import GlobalCompany

    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test contact@example.com")
    company = GlobalCompany(country="US", exchange="NASDAQ", currency="USD", ticker="BTBD", name="BT BRANDS, INC.")
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 1718224)
    accession = "0001477932-25-002248"

    def concept(value, end, *, accn=accession, start=None):
        row = {"val": value, "end": end, "accn": accn, "filed": "2025-03-31", "form": "10-K", "fp": "FY", "fy": 2024}
        if start:
            row["start"] = start
        return {"units": {"USD": [row]}}

    payload = {"entityName": "BT BRANDS, INC.", "facts": {"us-gaap": {
        "Assets": concept(11_996_797, "2024-12-31"),
        "Liabilities": concept(5_031_570, "2024-12-31"),
        "StockholdersEquity": concept(6_965_227, "2024-12-31"),
        "Revenues": concept(14_823_472, "2024-12-29", start="2024-01-01"),
        "NetIncomeLoss": concept(-2_311_208, "2024-12-29", start="2024-01-01"),
    }}}
    monkeypatch.setattr(provider, "_get_json", lambda url: payload)
    result = provider.enrich_fundamentals(company)
    assert result.revenue == 14_823_472
    assert result.net_income == -2_311_208
    assert result.filing_period_end == "2024-12-31"

    # A different accession cannot borrow income figures even two days apart.
    payload["facts"]["us-gaap"]["Revenues"] = concept(14_823_472, "2024-12-29", accn="different", start="2024-01-01")
    payload["facts"]["us-gaap"]["NetIncomeLoss"] = concept(-2_311_208, "2024-12-29", accn="different", start="2024-01-01")
    result = provider.enrich_fundamentals(company)
    assert result.revenue is None
    assert result.net_income is None


_BTBD_IXBRL = """<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:iso4217="http://www.xbrl.org/2003/iso4217"><body>
<ix:header><ix:resources>
<xbrli:context id="c_fy"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">{cik}</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2024-12-30</xbrli:startDate><xbrli:endDate>2025-12-28</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="c_prior"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">{cik}</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-29</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="c_end"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">{cik}</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2025-12-28</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="c_seg"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">{cik}</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">x:AMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2024-12-30</xbrli:startDate><xbrli:endDate>2025-12-28</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
</ix:resources></ix:header>
<ix:nonFraction name="us-gaap:Revenues" contextRef="c_fy" unitRef="usd" decimals="0">13,486,629</ix:nonFraction>
<ix:nonFraction name="us-gaap:Revenues" contextRef="c_prior" unitRef="usd" decimals="0">14,823,472</ix:nonFraction>
<ix:nonFraction name="us-gaap:Revenues" contextRef="c_seg" unitRef="usd" decimals="0">99,999,999</ix:nonFraction>
<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="c_fy" unitRef="usd" decimals="0" sign="-">687,839</ix:nonFraction>
<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="c_prior" unitRef="usd" decimals="0" sign="-">2,311,208</ix:nonFraction>
<ix:nonFraction name="us-gaap:Assets" contextRef="c_end" unitRef="usd" decimals="0">10,745,052</ix:nonFraction>
<ix:nonFraction name="us-gaap:Liabilities" contextRef="c_end" unitRef="usd" decimals="0">4,326,664</ix:nonFraction>
<ix:nonFraction name="us-gaap:StockholdersEquity" contextRef="c_end" unitRef="usd" decimals="0">6,418,388</ix:nonFraction>
</body></html>"""


def test_ixbrl_document_parser_is_strict_about_identity_and_dimensions():
    from global_markets.sec_filing_instance import parse_ixbrl_document

    html = _BTBD_IXBRL.format(cik="0001718224").encode()
    facts = parse_ixbrl_document(html, cik=1718224, form="10-K", filed="2026-03-30", accession="0001477932-26-001755")
    revenue = {row["end"]: row["val"] for row in facts["Revenues"]["units"]["USD"]}
    assert revenue == {"2025-12-28": 13_486_629, "2024-12-29": 14_823_472}  # segment fact excluded
    assert facts["NetIncomeLoss"]["units"]["USD"][0]["accn"] == "0001477932-26-001755"
    # A document filed under another entity's identifier yields nothing.
    other = _BTBD_IXBRL.format(cik="0000000042").encode()
    assert parse_ixbrl_document(other, cik=1718224, form="10-K", filed="2026-03-30") == {}


def test_btbd_newer_10k_read_from_ixbrl_when_companyfacts_lags_and_instance_malformed(monkeypatch):
    from global_markets.models import GlobalCompany
    from global_markets.sec_filing_instance import SECFilingInstanceReader

    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test contact@example.com")
    company = GlobalCompany(country="US", exchange="NASDAQ", currency="USD", ticker="BTBD", name="BT BRANDS, INC.")
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 1718224)
    old = "0001477932-25-002248"

    def concept(value, end, start=None):
        row = {"val": value, "end": end, "accn": old, "filed": "2025-03-31", "form": "10-K", "fp": "FY", "fy": 2024}
        if start:
            row["start"] = start
        return {"units": {"USD": [row]}}

    facts = {"us-gaap": {
        "Assets": concept(11_996_797, "2024-12-31"), "Liabilities": concept(5_031_570, "2024-12-31"),
        "StockholdersEquity": concept(6_965_227, "2024-12-31"),
        "Revenues": concept(14_823_472, "2024-12-31", "2024-01-01"),
        "NetIncomeLoss": concept(-2_311_208, "2024-12-31", "2024-01-01"),
    }}
    submissions = {"filings": {"recent": {
        "form": ["10-K", "10-K/A"], "isXBRL": [1, 1],
        "accessionNumber": ["0001477932-26-001755", "0001477932-25-003198"],
        "reportDate": ["2025-12-28", "2024-12-29"], "filingDate": ["2026-03-30", "2025-05-01"],
        "primaryDocument": ["btbd_10k.htm", "btbd_10ka.htm"],
    }}}

    def get_json(url):
        if "submissions" in url:
            return submissions
        if url.endswith("index.json"):
            return {"directory": {"item": [{"name": "btbd_10k_htm.xml"}]}}
        return {"entityName": "BT BRANDS, INC.", "facts": facts}

    def get_bytes(self, url):
        if url.endswith("_htm.xml"):
            return b"<xbrl><unterminated"  # SEC-extracted instance not well-formed
        return _BTBD_IXBRL.format(cik="0001718224").encode()

    monkeypatch.setattr(provider, "_get_json", get_json)
    monkeypatch.setattr(SECFilingInstanceReader, "_get_bytes", get_bytes)
    result = provider.enrich_fundamentals(company)
    assert result.filing_period_end == "2025-12-28"
    assert (result.revenue, result.net_income) == (13_486_629, -687_839)
    assert result.total_assets - result.total_liabilities == result.total_equity

    # Without a newer filed 10-K the old, stale period stays as-is (no invention).
    submissions["filings"]["recent"]["isXBRL"] = [0, 0]
    stale = provider.enrich_fundamentals(company)
    assert stale.filing_period_end == "2024-12-31"
