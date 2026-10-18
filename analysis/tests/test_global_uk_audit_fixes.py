"""UK (LSE) evidence fixes from the 2026-10-18 full-universe audit.

1. A London-listed issuer with a non-UK ISIN (Canal+, FR) lodges its tagged
   ESEF annual report with the FCA NSM although the home-state OAM lists none:
   the NSM is tried after the home OAM, for GB listings only.
2. Rathbones FY2025 is lodged as an ``.xbri`` ESEF package; the NSM locator
   used to drop every link not ending in zip/xhtml/html.
3. Filers that tag no ProfitLoss total (Regional REIT, Rainbow Rare Earths)
   get a labelled net income = profit before tax - income tax, UK only.
"""
from __future__ import annotations

from datetime import date

import pytest

from global_markets.esef import ESEFFundamentalsProvider
from global_markets.models import GlobalCompany
from global_markets.oam_esef import NationalOAMESEFProvider, OAMFiling, OAMLocator, UKNSMLocator
from global_markets.providers import GlobalProviderError

LEI = "9695000537F9F73BXN18"


class _Home(OAMLocator):
    oam = "fr-test"
    country = "FR"

    def __init__(self):
        pass

    def annual_filings(self, company, lei, legal_name):
        raise GlobalProviderError("AMF info-financiere lists no ESEF annual financial report")


class _Nsm(UKNSMLocator):
    def __init__(self, filings=None):
        self.filings = filings if filings is not None else [
            OAMFiling(oam="gb-fca-nsm", document_id="FCA-NSM:NI-1", package_url="https://x/NI-1.zip", landing_url="https://x")
        ]

    def annual_filings(self, company, lei, legal_name):
        return self.filings


def test_nsm_locator_accepts_xbri_report_packages():
    import json
    from global_markets.oam_esef import OAMHttp

    def hit(link, ident):
        return {"_source": {"lei": LEI, "type": "Annual Financial Report", "download_link": link, "tag_esef": "Tagged",
                            "publication_date": "2026-04-02T00:00:00Z", "disclosure_id": ident, "company": "X"}}

    payload = {"hits": {"hits": [hit(f"NSM/DirectUpload/NI-9/NI-9_{LEI}-2025-12-31.xbri", "NI-9"), hit("NSM/x/NI-8.pdf", "NI-8")]}}
    locator = UKNSMLocator(OAMHttp())
    locator.http.cached_text = lambda key, fetch: json.dumps(payload)  # type: ignore[method-assign]
    filings = locator.annual_filings(_company(), LEI, "X")
    assert [f.document_id for f in filings] == ["FCA-NSM:NI-9"]


def _company(country="GB", isin="FR001400T0D6"):
    return GlobalCompany(country=country, exchange="LSE", currency="GBP", ticker="CAN", name="CANAL+", isin=isin)


def test_gb_listing_with_foreign_isin_tries_home_oam_then_nsm():
    provider = NationalOAMESEFProvider(locators=[_Home(), _Nsm()])
    order = [loc.country for loc in provider.locators_for(_company())]
    assert order == ["FR", "GB"]


def test_gb_isin_uses_nsm_once():
    provider = NationalOAMESEFProvider(locators=[_Home(), _Nsm()])
    assert [loc.country for loc in provider.locators_for(_company(isin="GB00B1YW4409"))] == ["GB"]


def test_non_gb_listing_never_gets_nsm_fallback():
    provider = NationalOAMESEFProvider(locators=[_Home(), _Nsm()])
    company = _company(country="NL", isin="FR001400T0D6")
    assert [loc.country for loc in provider.locators_for(company)] == ["FR"]


def test_nsm_filing_is_used_when_home_oam_has_none(monkeypatch):
    provider = NationalOAMESEFProvider(locators=[_Home(), _Nsm()])
    monkeypatch.setattr(provider, "_resolve_lei", lambda company: (LEI, "CANAL+"))
    seen = []

    def package_facts(filing):
        seen.append(filing.document_id)
        return {"facts": [], "entities": []}

    monkeypatch.setattr(provider, "package_facts", package_facts)
    with pytest.raises(GlobalProviderError) as info:
        provider.enrich_fundamentals(_company())
    # The NSM filing was actually reached; both OAM failures are reported.
    assert seen == ["FCA-NSM:NI-1"]
    assert "fr-test: AMF info-financiere lists no ESEF" in str(info.value)
    assert "no inline XBRL" in str(info.value)


def test_nsm_fallback_keeps_the_lei_hard_gate(monkeypatch):
    provider = NationalOAMESEFProvider(locators=[_Home(), _Nsm()])
    monkeypatch.setattr(provider, "_resolve_lei", lambda company: (LEI, "CANAL+"))
    monkeypatch.setattr(provider, "package_facts", lambda filing: {"facts": [{"x": 1}], "entities": ["549300OTHERENTITY0000"]})
    with pytest.raises(GlobalProviderError, match="report entity .* != LEI"):
        provider.enrich_fundamentals(_company())


def test_single_locator_error_is_unchanged():
    provider = NationalOAMESEFProvider(locators=[_Home()])
    with pytest.raises(GlobalProviderError) as info:
        provider.enrich_fundamentals(_company(country="FR"))
    assert str(info.value) == "AMF info-financiere lists no ESEF annual financial report"


def fact(concept, value, period, unit="iso4217:GBP"):
    return {"value": str(value), "dimensions": {"concept": concept, "entity": "scheme:LEI", "period": period, "unit": unit}}


YEAR = "2025-01-01T00:00:00/2026-01-01T00:00:00"
PRIOR = "2024-01-01T00:00:00/2025-01-01T00:00:00"
END = date(2025, 12, 31)


def _reit_facts(extra=()):
    return [
        fact("ifrs-full:ProfitLossBeforeTax", -16_366_000, YEAR),
        fact("ifrs-full:IncomeTaxExpenseContinuingOperations", -14_000, YEAR),
        fact("ifrs-full:ProfitLossBeforeTax", -39_474_000, PRIOR),
        fact("ifrs-full:IncomeTaxExpenseContinuingOperations", 65_000, PRIOR),
        fact("ifrs-full:Assets", 500_000_000, "2026-01-01T00:00:00"),
        fact("ifrs-full:Equity", 250_000_000, "2026-01-01T00:00:00"),
        *extra,
    ]


def test_net_income_derived_from_pretax_minus_tax_for_uk():
    result = ESEFFundamentalsProvider().normalized_fields(_reit_facts(), END, derive_net_income=True)
    meta = result.pop("__normalization_meta__")
    assert result["net_income"] == -16_352_000
    assert meta["net_income_method"] == "derived_profit_before_tax_minus_income_tax_same_period"


def test_derivation_is_off_by_default_so_other_markets_are_unchanged():
    result = ESEFFundamentalsProvider().normalized_fields(_reit_facts(), END)
    assert result["net_income"] is None
    assert result["__normalization_meta__"]["net_income_method"] is None


def test_direct_profit_loss_tag_always_wins():
    facts = _reit_facts([fact("ifrs-full:ProfitLoss", -1_000, YEAR)])
    result = ESEFFundamentalsProvider().normalized_fields(facts, END, derive_net_income=True)
    assert result["net_income"] == -1_000
    assert result["__normalization_meta__"]["net_income_method"] == "direct_profit_loss_tag"


def test_filings_that_already_have_revenue_keep_their_values():
    facts = _reit_facts([fact("ifrs-full:Revenue", 1_000_000, YEAR)])
    result = ESEFFundamentalsProvider().normalized_fields(facts, END, derive_net_income=True)
    assert result["net_income"] is None
    assert result["__normalization_meta__"]["net_income_method"] is None


def test_not_derived_with_discontinued_result_or_missing_tax():
    p = ESEFFundamentalsProvider()
    discontinued = _reit_facts([fact("ifrs-full:ProfitLossFromDiscontinuedOperations", 5_000_000, YEAR)])
    assert p.normalized_fields(discontinued, END, derive_net_income=True)["net_income"] is None
    no_tax = [f for f in _reit_facts() if f["dimensions"]["concept"] != "ifrs-full:IncomeTaxExpenseContinuingOperations"]
    assert p.normalized_fields(no_tax, END, derive_net_income=True)["net_income"] is None


def test_lse_official_digit_led_ordinary_is_analysable_like_the_catalog_lists_it():
    from global_markets.service import _supported_operating_equity

    raw = {"official_universe": True, "lse_description": "FIRST TIN PLC ORD 1P"}
    official = GlobalCompany(country="GB", exchange="LSE", currency="GBP", ticker="1SN", name="FIRST TIN PLC",
                             isin="GB00BNR45554", raw_provider_fields=raw)
    assert _supported_operating_equity(official) is True
    # Without the LSE adapter's certification the digit-led guard still applies.
    assert _supported_operating_equity(GlobalCompany(country="GB", exchange="LSE", currency="GBP", ticker="1SN",
                                                     name="FIRST TIN PLC")) is False
    # Structural guards still win over the certification (e.g. a preference line).
    pref = GlobalCompany(country="GB", exchange="LSE", currency="GBP", ticker="BP.PR", name="BP PLC",
                         raw_provider_fields=raw)
    assert _supported_operating_equity(pref) is False
