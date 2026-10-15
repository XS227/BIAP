import pytest

from global_markets.models import GlobalCompany
from global_markets.sec_edgar import SECEdgarFundamentalsProvider


def _concept(value, *, end="2025-12-31", filed="2026-02-20", unit="USD", form="10-K"):
    return {"units": {unit: [{"form": form, "fp": "FY", "fy": 2025, "start": "2025-01-01",
                              "end": end, "filed": filed, "val": value}]}}


def _dei(rows):
    return {"EntityCommonStockSharesOutstanding": {"units": {"shares": rows}}}


def _row(val, end="2026-02-10", form="10-K", filed="2026-02-20"):
    return {"form": form, "end": end, "filed": filed, "val": val}


def _enrich(monkeypatch, dei_rows, gaap_extra=None):
    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test test@example.com")
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 200406)
    gaap = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(88_000_000_000),
        "NetIncomeLoss": _concept(14_000_000_000),
        "Assets": _concept(180_000_000_000),
        **(gaap_extra or {}),
    }
    facts = {"us-gaap": gaap}
    if dei_rows is not None:
        facts["dei"] = _dei(dei_rows)
    monkeypatch.setattr(provider, "_get_json", lambda url: {"entityName": "Test Corp", "facts": facts})
    company = GlobalCompany(country="US", exchange="NYSE", mic_code="XNYS", currency="USD",
                            ticker="TEST", name="Test Corp")
    return provider.enrich_fundamentals(company)


def test_cover_page_count_used_when_gaap_shares_missing_and_labelled(monkeypatch):
    enriched = _enrich(monkeypatch, [_row(2_409_898_597)])
    assert enriched.shares_outstanding == 2_409_898_597.0
    assert enriched.raw_provider_fields["shares_outstanding_basis"] == "sec_dei_cover_page:10-K:2026-02-10"


def test_gaap_shares_concept_wins_over_cover_page(monkeypatch):
    enriched = _enrich(
        monkeypatch, [_row(999)],
        {"CommonStockSharesOutstanding": _concept(2_400_000_000, unit="shares")},
    )
    assert enriched.shares_outstanding == 2_400_000_000.0
    assert "shares_outstanding_basis" not in enriched.raw_provider_fields


def test_multiple_share_classes_on_cover_are_withheld(monkeypatch):
    enriched = _enrich(monkeypatch, [_row(2_200_000_000), _row(340_000_000)])
    assert enriched.shares_outstanding is None


def test_cover_page_before_fiscal_period_end_is_withheld(monkeypatch):
    enriched = _enrich(monkeypatch, [_row(5_000_000, end="2025-06-30", form="10-Q")])
    assert enriched.shares_outstanding is None


@pytest.mark.parametrize("form", ["20-F", "40-F"])
def test_foreign_private_issuer_cover_counts_are_withheld(monkeypatch, form):
    enriched = _enrich(monkeypatch, [_row(5_000_000, form=form)])
    assert enriched.shares_outstanding is None


def test_missing_dei_leaves_shares_unavailable(monkeypatch):
    assert _enrich(monkeypatch, None).shares_outstanding is None
