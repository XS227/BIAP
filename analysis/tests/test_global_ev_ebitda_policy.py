import pytest

from global_markets.models import GlobalCompany
from global_markets.service import _derive_metrics


def _co(**kw):
    base = dict(country="US", exchange="NASDAQ", mic_code="XNAS", currency="USD", ticker="T", name="T",
                price=50.0, reporting_currency="USD", shares_outstanding=100_000_000, ebitda=500_000_000,
                total_debt=300_000_000, cash_and_equivalents=100_000_000)
    base.update(kw)
    return GlobalCompany(**base)


def test_ev_ebitda_derived_when_all_inputs_present():
    out = _derive_metrics(_co())
    assert out.ev_ebitda == pytest.approx((5e9 + 3e8 - 1e8) / 5e8)
    assert "ratio_anomalies" not in out.raw_provider_fields


@pytest.mark.parametrize("missing,label", [("total_debt", "total_debt"), ("cash_and_equivalents", "cash_and_equivalents")])
def test_missing_enterprise_value_input_is_withheld_not_zeroed(missing, label):
    out = _derive_metrics(_co(**{missing: None}))
    assert out.ev_ebitda is None
    notes = out.raw_provider_fields["derived_metrics"]
    assert any(n.startswith("ev_ebitda_withheld:enterprise_value_input_missing(") and label in n for n in notes)


def test_extreme_multiple_is_flagged_and_value_kept():
    out = _derive_metrics(_co(ebitda=5_000_000))  # EV 5.2bn / 5m = 1040x
    assert out.ev_ebitda == pytest.approx(5.2e9 / 5e6)
    flag = out.raw_provider_fields["ratio_anomalies"][0]
    assert flag["metric"] == "ev_ebitda" and flag["action"] == "flagged_value_retained"


def test_provider_supplied_extreme_multiple_is_flagged_not_deleted():
    out = _derive_metrics(_co(ev_ebitda=553.0, ebitda=None))
    assert out.ev_ebitda == 553.0
    assert out.raw_provider_fields["ratio_anomalies"][0]["value"] == 553.0


def _nonstd(value=400_000_000):
    return {"nonstandard_metrics": {"ebitda_incl_impairment": value, "standard": False,
            "formula": "operating_income + abs(ifrs-full:DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss)",
            "sourceConcept": "ifrs-full:DepreciationAmortisationAndImpairment", "fiscalPeriodEnd": "2025-12-31", "confidence": 0.6}}


def test_impairment_inclusive_multiple_is_separate_and_never_standard():
    out = _derive_metrics(_co(ebitda=None, raw_provider_fields=_nonstd()))
    assert out.ev_ebitda is None and out.ebitda is None
    adj = out.raw_provider_fields["adjusted_metrics"]["ev_ebitda_incl_impairment"]
    assert adj["value"] == pytest.approx((5e9 + 3e8 - 1e8) / 4e8)
    assert adj["standard"] is False and adj["label"].startswith("ADJUSTED, NON-STANDARD")
    assert adj["sourceConcept"] == "ifrs-full:DepreciationAmortisationAndImpairment" and adj["fiscalPeriodEnd"] == "2025-12-31"


def test_adjusted_multiple_not_produced_when_standard_ebitda_exists_or_inputs_missing():
    assert "adjusted_metrics" not in _derive_metrics(_co(raw_provider_fields=_nonstd())).raw_provider_fields
    assert "adjusted_metrics" not in _derive_metrics(_co(ebitda=None, total_debt=None, raw_provider_fields=_nonstd())).raw_provider_fields
