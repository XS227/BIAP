"""Annual 20-F/40-F XBRL instance supplement when SEC companyfacts lags."""
from __future__ import annotations

import pytest

from global_markets import sec_filing_instance, sec_foreign_ifrs
from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError
from global_markets.sec_filing_instance import annual_xbrl_filings, instance_candidates, parse_instance
from global_markets.sec_foreign_ifrs import SECForeignIFRSFundamentalsProvider
from global_markets.sec_identity import identity_matches, sec_core

CIK = 1046179
ACCESSION = "0001628280-26-025362"
FOLDER = f"https://www.sec.gov/Archives/edgar/data/{CIK}/000162828026025362"
INSTANCE_URL = f"{FOLDER}/tsm-20251231_htm.xml"


def _context(cid, *, start=None, end=None, instant=None, cik=CIK, member=None):
    segment = (
        f'<segment><xbrldi:explicitMember dimension="ifrs-full:SegmentsAxis">{member}</xbrldi:explicitMember></segment>'
        if member else ""
    )
    period = f"<instant>{instant}</instant>" if instant else f"<startDate>{start}</startDate><endDate>{end}</endDate>"
    return (
        f'<context id="{cid}"><entity><identifier scheme="http://www.sec.gov/CIK">{cik:010d}</identifier>'
        f"{segment}</entity><period>{period}</period></context>"
    )


def instance(*, cik=CIK) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:ifrs-full="https://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full"
      xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xmlns:tsm="http://www.tsmc.com/20251231">
  {_context("fy25", start="2025-01-01", end="2025-12-31", cik=cik)}
  {_context("fy24", start="2024-01-01", end="2024-12-31", cik=cik)}
  {_context("q4", start="2025-10-01", end="2025-12-31", cik=cik)}
  {_context("seg", start="2025-01-01", end="2025-12-31", cik=cik, member="tsm:WaferMember")}
  {_context("i25", instant="2025-12-31", cik=cik)}
  <unit id="TWD"><measure>iso4217:TWD</measure></unit>
  <unit id="TWDps"><divide><unitNumerator><measure>iso4217:TWD</measure></unitNumerator>
    <unitDenominator><measure>xbrli:shares</measure></unitDenominator></divide></unit>
  <ifrs-full:Revenue contextRef="fy25" unitRef="TWD" decimals="-5">3809054000000</ifrs-full:Revenue>
  <ifrs-full:Revenue contextRef="fy24" unitRef="TWD" decimals="-5">2894307700000</ifrs-full:Revenue>
  <ifrs-full:Revenue contextRef="q4" unitRef="TWD" decimals="-5">1046090000000</ifrs-full:Revenue>
  <ifrs-full:Revenue contextRef="seg" unitRef="TWD" decimals="-5">1</ifrs-full:Revenue>
  <ifrs-full:ProfitLoss contextRef="fy25" unitRef="TWD" decimals="-5">1717898000000</ifrs-full:ProfitLoss>
  <ifrs-full:ProfitLoss contextRef="fy24" unitRef="TWD" decimals="-5">1157523900000</ifrs-full:ProfitLoss>
  <ifrs-full:Assets contextRef="i25" unitRef="TWD" decimals="-5">7900000000000</ifrs-full:Assets>
  <ifrs-full:Equity contextRef="i25" unitRef="TWD" decimals="-5">5200000000000</ifrs-full:Equity>
  <ifrs-full:Liabilities contextRef="i25" unitRef="TWD" xsi:nil="true"/>
  <ifrs-full:DilutedEarningsLossPerShare contextRef="fy25" unitRef="TWDps" decimals="2">66.25</ifrs-full:DilutedEarningsLossPerShare>
  <unit id="USD"><measure>iso4217:USD</measure></unit>
  <ifrs-full:Revenue contextRef="fy25" unitRef="USD" decimals="-5">121000000000</ifrs-full:Revenue>
  <ifrs-full:Assets contextRef="i25" unitRef="USD" decimals="-5">252000000000</ifrs-full:Assets>
  <tsm:CustomRevenue contextRef="fy25" unitRef="TWD">5</tsm:CustomRevenue>
</xbrl>""".encode()


def row(val, end, filed, unit_form="20-F"):
    return {"val": val, "end": end, "filed": filed, "form": unit_form, "fp": "FY"}


LAGGING_COMPANYFACTS = {
    "entityName": "Taiwan Semiconductor Manufacturing Company Limited",
    "facts": {"ifrs-full": {
        "Revenue": {"units": {"TWD": [row(2894307700000, "2024-12-31", "2025-04-17")]}},
        "ProfitLoss": {"units": {"TWD": [row(1157523900000, "2024-12-31", "2025-04-17")]}},
        "Assets": {"units": {"TWD": [row(6691764700000, "2024-12-31", "2025-04-17")]}},
    }},
}


def submissions(report_date="2025-12-31", is_xbrl=1, form="20-F"):
    return {"filings": {"recent": {
        "form": ["6-K", form, "20-F"],
        "accessionNumber": ["0001046179-26-000660", ACCESSION, "0001628280-25-000001"],
        "reportDate": ["2026-08-31", report_date, "2024-12-31"],
        "filingDate": ["2026-09-24", "2026-04-16", "2025-04-17"],
        "primaryDocument": ["x.htm", "tsm-20251231.htm", "tsm-20241231.htm"],
        "isXBRL": [0, is_xbrl, 1],
    }}}


def tsm():
    return GlobalCompany(
        country="US", exchange="NYSE", mic_code="XNYS", currency="USD", ticker="TSM",
        name="Taiwan Semiconductor Manufacturing Company Ltd.",
    )


def provider_with(monkeypatch, *, subs, body=None):
    provider = SECForeignIFRSFundamentalsProvider(user_agent="BIAP test contact@example.com")
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: CIK)
    fetched = []

    def get_json(url):
        fetched.append(url)
        if "/submissions/" in url:
            return subs
        if url.endswith("/index.json"):
            return {"directory": {"item": [{"name": "tsm-20251231.htm"}, {"name": "tsm-20251231_htm.xml"}]}}
        return LAGGING_COMPANYFACTS

    monkeypatch.setattr(provider, "_get_json", get_json)
    monkeypatch.setattr(
        sec_filing_instance.SECFilingInstanceReader, "_get_bytes",
        lambda self, url: (fetched.append(url) or (body if body is not None else instance())),
    )
    return provider, fetched


def test_parse_instance_keeps_only_non_dimensional_annual_ifrs_facts():
    facts = parse_instance(instance(), cik=CIK, form="20-F", filed="2026-04-16")
    revenue = facts["Revenue"]["units"]["TWD"]
    assert sorted((r["end"], r["val"]) for r in revenue) == [
        ("2024-12-31", 2894307700000), ("2025-12-31", 3809054000000)]
    assert all(r["form"] == "20-F" and r["fp"] == "FY" and r["filed"] == "2026-04-16" for r in revenue)
    assert facts["DilutedEarningsLossPerShare"]["units"]["TWD/shares"][0]["val"] == 66.25
    assert "Liabilities" not in facts  # nil
    assert all(set(body["units"]) <= {"TWD", "TWD/shares"} for body in facts.values())  # USD convenience column
    assert "CustomRevenue" not in facts  # issuer extension, not ifrs-full


def test_parse_instance_rejects_foreign_cik_contexts():
    assert parse_instance(instance(cik=999), cik=CIK, form="20-F", filed="2026-04-16") == {}


def test_annual_xbrl_filings_and_instance_url():
    rows = annual_xbrl_filings(submissions())
    assert [r["accession"] for r in rows] == [ACCESSION, "0001628280-25-000001"]
    index = {"directory": {"item": [{"name": "tsm-20251231.htm"}, {"name": "tsm-20251231_htm.xml"}]}}
    assert instance_candidates(CIK, rows[0], index) == [INSTANCE_URL]
    assert annual_xbrl_filings(submissions(is_xbrl=0))[0]["accession"] == "0001628280-25-000001"


def test_lagging_companyfacts_uses_newer_filed_20f_instance(monkeypatch):
    provider, fetched = provider_with(monkeypatch, subs=submissions())
    enriched = provider.enrich_fundamentals(tsm())
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.filing_observed_at == "2026-04-16"
    assert enriched.revenue == 3809054000000
    assert enriched.revenue_prev == 2894307700000
    assert enriched.net_income == 1717898000000
    assert enriched.total_assets == 7900000000000
    assert enriched.reporting_currency == "TWD"
    assert enriched.raw_provider_fields["sec_instance_accession"] == ACCESSION
    source = next(s for s in enriched.sources if s.provider == provider.provider_id)
    assert source.source_type == "official_regulatory_xbrl"
    assert source.source_url == INSTANCE_URL
    assert "filed SEC XBRL instance" in source.notes
    assert INSTANCE_URL in fetched


def test_no_newer_annual_filing_keeps_stale_rejection(monkeypatch):
    provider, fetched = provider_with(monkeypatch, subs=submissions(report_date="2024-12-31"))
    with pytest.raises(GlobalProviderError, match="stale"):
        provider.enrich_fundamentals(tsm())
    assert not any(url.endswith(".xml") for url in fetched)


def test_instance_with_wrong_cik_does_not_rescue_stale_companyfacts(monkeypatch):
    provider, _ = provider_with(monkeypatch, subs=submissions(), body=instance(cik=999))
    with pytest.raises(GlobalProviderError, match="stale"):
        provider.enrich_fundamentals(tsm())


def test_fresh_companyfacts_does_not_query_submissions(monkeypatch):
    provider, fetched = provider_with(monkeypatch, subs=submissions())
    fresh = {"entityName": LAGGING_COMPANYFACTS["entityName"], "facts": {"ifrs-full": {
        "Revenue": {"units": {"TWD": [row(3809054000000, "2025-12-31", "2026-04-16")]}},
    }}}
    monkeypatch.setattr(provider, "_get_json", lambda url: fetched.append(url) or fresh)
    assert provider.enrich_fundamentals(tsm()).filing_period_end == "2025-12-31"
    assert not any("/submissions/" in url for url in fetched)


def test_us_catalog_listing_markers_do_not_break_exact_identity():
    assert identity_matches("BP PLC", ["BP p.l.c. Common Stock"])
    assert identity_matches("United Microelectronics Corporation", ["United Microelectronics Corporation (NEW) Common Stock"])
    assert sec_core("Newmont Corporation") == "NEWMONT"
    assert not identity_matches("BP Prudhoe Bay Royalty Trust", ["BP p.l.c. Common Stock"])


class _FrozenDate(sec_foreign_ifrs.date):
    today_value = None

    @classmethod
    def today(cls):
        return cls.today_value


def test_newer_instance_that_is_itself_stale_is_still_rejected(monkeypatch):
    # Companyfacts (FY2024) and the newer filed 20-F instance (FY2025) are both
    # older than the freshness limit: the instance closes the ingestion gap but
    # must never make a stale filing look current.
    _FrozenDate.today_value = sec_foreign_ifrs.date(2027, 9, 1)
    monkeypatch.setattr(sec_foreign_ifrs, "date", _FrozenDate)
    provider, fetched = provider_with(monkeypatch, subs=submissions())
    with pytest.raises(GlobalProviderError, match="stale: period_end=2025-12-31"):
        provider.enrich_fundamentals(tsm())
    assert INSTANCE_URL in fetched


def test_submissions_failure_keeps_stale_rejection(monkeypatch):
    provider, _ = provider_with(monkeypatch, subs=submissions())

    def get_json(url):
        if "/submissions/" in url:
            raise GlobalProviderError("SEC submissions HTTP 503")
        return LAGGING_COMPANYFACTS

    monkeypatch.setattr(provider, "_get_json", get_json)
    with pytest.raises(GlobalProviderError, match="stale: period_end=2024-12-31"):
        provider.enrich_fundamentals(tsm())
