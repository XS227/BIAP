from dataclasses import replace
from datetime import date

from global_markets.esef import ESEFFundamentalsProvider
from global_markets.models import GlobalCompany
from global_markets.service import _derive_metrics

END = date(2025, 12, 31)
INSTANT = "2025-12-31"


def fact(concept, value, period=INSTANT, unit="xbrli:shares", **dims):
    return {"value": str(value), "dimensions": {"concept": concept, "entity": "scheme:LEI", "period": period, "unit": unit, **dims}}


def norm(facts):
    return ESEFFundamentalsProvider().normalized_fields(facts, END)


def test_single_class_issued_is_accepted_and_labelled():
    r = norm([fact("ifrs-full:NumberOfSharesIssued", 1_000_000)])
    assert r["shares_outstanding"] == 1_000_000
    assert r["__normalization_meta__"]["shares_outstanding_basis"] == "issued_single_class_fallback"


def test_outstanding_is_preferred_and_unlabelled():
    r = norm([fact("ifrs-full:NumberOfSharesIssued", 1_000_000), fact("ifrs-full:NumberOfSharesOutstanding", 950_000)])
    assert r["shares_outstanding"] == 950_000
    assert "shares_outstanding_basis" not in r["__normalization_meta__"]


def test_per_class_facts_withhold():
    r = norm([
        fact("ifrs-full:NumberOfSharesIssued", 1_000_000),
        fact("ifrs-full:NumberOfSharesIssued", 400_000, **{"ifrs-full:ClassesOfOrdinarySharesAxis": "x:ClassAMember"}),
    ])
    assert "shares_outstanding" not in r


def test_wrong_date_conflicting_or_bad_unit_withhold():
    assert "shares_outstanding" not in norm([fact("ifrs-full:NumberOfSharesIssued", 1, period="2024-12-31")])
    assert "shares_outstanding" not in norm([fact("ifrs-full:NumberOfSharesIssued", 1), fact("ifrs-full:NumberOfSharesIssued", 2)])
    assert "shares_outstanding" not in norm([fact("ifrs-full:NumberOfSharesIssued", 1, unit="iso4217:EUR")])
    assert "shares_outstanding" not in norm([fact("ifrs-full:NumberOfSharesIssued", 0)])


def _company(ticker, basis="issued_single_class_fallback"):
    return GlobalCompany(
        country="SE", exchange="NASDAQ_STOCKHOLM", currency="SEK", ticker=ticker, name="X AB",
        price=100.0, shares_outstanding=1_000_000.0, reporting_currency="SEK",
        raw_provider_fields={"oam_credit_extraction": {"shares_outstanding_basis": basis}},
    )


def test_market_cap_derived_and_labelled_for_single_class():
    c = _derive_metrics(_company("ABCD"))
    assert c.market_cap == 100_000_000.0
    assert any("labelled fallback" in note for note in c.raw_provider_fields["derived_metrics"])


def test_class_suffixed_ticker_never_gets_issued_based_market_cap():
    for ticker in ("VOLV.B", "ATCO.A", "OCTV.SDB"):
        c = _derive_metrics(_company(ticker))
        assert c.market_cap is None
        assert any("shares_withheld" in n for n in c.raw_provider_fields["derived_metrics"])
