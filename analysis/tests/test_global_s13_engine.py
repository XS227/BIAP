"""Session 13 regression set: Volvo Car AB (VOLCAR.B) FY2025 and the six-market fixes.

Volvo Car is the audit case: ProfitLoss -2,968m but owners' profit +174m (non-controlling
interests -3,142m), EPS +0.06, EBIT 303m vs interest 1,251m (ICR 0.24x), EBITDA 24,248m
(19.4x interest), Agent 10 grid AA-, Agent 9 HIGH_RISK.
"""
from dataclasses import replace
from datetime import date

import pytest

from global_markets import nasdaq_nordic_series as nns
from global_markets import service
from global_markets.cached_market import PersistentMarketProvider
from global_markets.credit_scoring import rating_consistency, score_legal_entity_company
from global_markets.distress import distress_agent
from global_markets.esef import ESEFFundamentalsProvider
from global_markets.market_cap_seed import market_cap_from_quote
from global_markets.models import GlobalCompany

DUR = "2025-01-01T00:00:00/2026-01-01T00:00:00"
INST = "2026-01-01T00:00:00"


def fact(concept, value, period, unit="iso4217:SEK"):
    return {"value": str(value), "dimensions": {"concept": concept, "entity": "scheme:LEI", "period": period, "unit": unit}}


def volvo_car(**over):
    base = dict(
        country="SE", exchange="NASDAQ_STOCKHOLM", mic_code="XSTO", currency="SEK", ticker="VOLCAR.B",
        name="Volvo Car AB", price=14.95, reporting_currency="SEK", eps=0.06,
        net_income=-2_968e6, revenue=357_263e6, operating_income=303e6, ebitda=24_248e6,
        total_assets=373_172e6, total_liabilities=224_794e6, total_equity=148_378e6,
        retained_earnings=101_347e6, current_assets=157_801e6, current_liabilities=151_254e6,
        cash_and_equivalents=57_564e6, operating_cash_flow=34_625e6, free_cash_flow=11_800e6,
        total_debt=30_790e6, interest_expense=1_251e6, filing_period_end="2025-12-31",
        raw_provider_fields={
            "nasdaq_orderbook_id": "TX4016914",
            "oam_credit_extraction": {"net_income_owners": 174e6},
            "agent10_ffo": 20_915e6,
        },
    )
    base.update(over)
    return GlobalCompany(**base)


UNIVERSE = [
    {"name": "Volvo Car B", "ticker": "VOLCAR.B", "raw_provider_fields": {"nasdaq_orderbook_id": "TX4016914"}},
    {"name": "Volvo A", "ticker": "VOLV.A", "raw_provider_fields": {"nasdaq_orderbook_id": "TX99"}},
    {"name": "Volvo B", "ticker": "VOLV.B", "raw_provider_fields": {"nasdaq_orderbook_id": "TX100"}},
]
SERIES = {
    "TX4016914": {"shares": 2_979_524_179.0, "market_cap": 44_543_886_476.0},
    "TX99": {"shares": 0.45e9, "market_cap": 142.7e9},
    "TX100": {"shares": 1.5927e9, "market_cap": 503.9e9},
}


@pytest.fixture
def series(monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_NORDIC_SERIES", "1")
    def fake_fetch(orderbook_id, **_):
        row = SERIES.get(orderbook_id)
        return None if row is None else {**row, "fetchedAt": "2026-10-13T00:00:00+00:00", "cache": "live"}

    monkeypatch.setattr(service, "resolve_issuer_value", lambda **kw: nns.resolve_issuer_value(**kw, universe=UNIVERSE, fetch=fake_fetch))


# --- ESEF extraction -------------------------------------------------------------------

def test_esef_records_owners_profit_next_to_consolidated_profit():
    result = ESEFFundamentalsProvider().normalized_fields([
        fact("ifrs-full:ProfitLoss", -2968, DUR),
        fact("ifrs-full:ProfitLossAttributableToOwnersOfParent", 174, DUR),
        fact("ifrs-full:Revenue", 357263, DUR),
    ], date(2025, 12, 31))
    meta = result.pop("__normalization_meta__")
    assert result["net_income"] == -2968
    assert meta["net_income_owners"] == 174
    assert meta["net_income_basis"].startswith("consolidated")


def _share_facts(was, eps=0.06, owners=174e6):
    return [
        fact("ifrs-full:ProfitLossAttributableToOwnersOfParent", owners, DUR),
        fact("ifrs-full:BasicEarningsLossPerShare", eps, DUR, "iso4217:SEK/xbrli:shares"),
        fact("ifrs-full:WeightedAverageShares", was, DUR, "xbrli:shares"),
        fact("ifrs-full:Revenue", 1000, DUR),
    ]


def test_weighted_average_shares_used_only_when_reconciled_to_eps():
    ok = ESEFFundamentalsProvider().normalized_fields(_share_facts(2.9e9), date(2025, 12, 31))
    assert ok["shares_outstanding"] == 2.9e9
    assert ok["__normalization_meta__"]["field_status"]["shares_outstanding"] == "extracted_weighted_average_basic_reconciled_to_eps"
    bad = ESEFFundamentalsProvider().normalized_fields(_share_facts(1.0e9), date(2025, 12, 31))
    assert "shares_outstanding" not in bad  # 174m / 0.06 = 2.9bn: a 1.0bn count does not reconcile


def test_weighted_average_shares_withheld_without_eps_to_reconcile():
    facts = [f for f in _share_facts(2.9e9) if "EarningsLoss" not in f["dimensions"]["concept"]]
    assert "shares_outstanding" not in ESEFFundamentalsProvider().normalized_fields(facts, date(2025, 12, 31))


def test_interest_bearing_and_lease_liabilities_outside_total_debt_are_recorded():
    result = ESEFFundamentalsProvider().normalized_fields([
        fact("ifrs-full:NoncurrentPortionOfNoncurrentBondsIssued", 21_645e6, INST),
        fact("ifrs-full:NoncurrentPortionOfNoncurrentLoansReceived", 6_723e6, INST),
        fact("VOL:OtherNonCurrentLiabilitiesInterestBearing", 5_355e6, INST),
        fact("VOL:OtherNonCurrentLiabilitiesNonInterestBearing", 6_714e6, INST),
        fact("ifrs-full:Revenue", 1000, DUR),
    ], date(2025, 12, 31))
    meta = result["__normalization_meta__"]
    assert result["total_debt"] == 28_368e6
    assert meta["debt_excluded_interest_bearing_liabilities"] == {"VOL:OtherNonCurrentLiabilitiesInterestBearing": 5_355e6}


# --- EPS / owners' profit / market cap -----------------------------------------------------

def test_owner_profit_explains_opposite_sign_of_consolidated_loss(series):
    out = service._derive_metrics(volvo_car())
    assert out.eps == 0.06 and out.pe == pytest.approx(14.95 / 0.06)
    notes = out.raw_provider_fields["derived_metrics"]
    assert any(n.startswith("eps_consistent_with_owners_profit") for n in notes)
    assert not any(n.startswith("eps_withheld") for n in notes)


def test_eps_sign_against_owner_profit_is_still_withheld(series):
    out = service._derive_metrics(volvo_car(eps=0.06, raw_provider_fields={"oam_credit_extraction": {"net_income_owners": -5e6}}))
    assert out.eps is None and out.pe is None


def test_single_listed_class_market_cap_reconciles_and_drives_ev_ebitda(series):
    out = service._derive_metrics(volvo_car())
    assert out.market_cap == pytest.approx(44_543_886_476.0)
    assert out.shares_outstanding == pytest.approx(2_979_524_179.0)
    expected_ev = 44_543_886_476.0 + 30_790e6 - 57_564e6
    assert out.ev_ebitda == pytest.approx(expected_ev / 24_248e6)


def test_dual_class_issuer_market_cap_is_the_sum_of_both_listed_classes(monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_NORDIC_SERIES", "1")
    def fake_fetch(orderbook_id, **_):
        return {**SERIES[orderbook_id], "fetchedAt": "x", "cache": "live"}

    monkeypatch.setattr(service, "resolve_issuer_value", lambda **kw: nns.resolve_issuer_value(**kw, universe=UNIVERSE, fetch=fake_fetch))
    volvo_ab = GlobalCompany(
        country="SE", exchange="NASDAQ_STOCKHOLM", currency="SEK", ticker="VOLV.B", name="Aktiebolaget Volvo",
        price=316.4, reporting_currency="SEK", eps=16.94, net_income=34_707e6,
        raw_provider_fields={"nasdaq_orderbook_id": "TX100", "oam_credit_extraction": {"net_income_owners": 34_456e6}},
    )
    out = service._derive_metrics(volvo_ab)
    assert out.market_cap == pytest.approx(142.7e9 + 503.9e9)  # A + B, not B alone
    assert out.shares_outstanding == pytest.approx(0.45e9 + 1.5927e9)
    assert out.raw_provider_fields["nordic_series"]["listed_classes"] == 2


def test_class_suffixed_issuer_with_unlisted_class_stays_unverified():
    universe = [{"name": "Foo B", "ticker": "FOO.B", "raw_provider_fields": {"nasdaq_orderbook_id": "T1"}}]
    fetch = lambda ob, **_: {"shares": 100e6, "market_cap": 1e9, "fetchedAt": "x", "cache": "live"}
    # owners' profit / EPS says the issuer has 150m shares; the listed class is only 100m
    res = nns.resolve_issuer_value(
        name="Foo AB", orderbook_id="T1", country="SE", exchange="NASDAQ_STOCKHOLM",
        reference_shares=150e6, reference_label="owners_profit_over_eps", universe=universe, fetch=fetch,
    )
    assert res["status"] == "unverified" and "unlisted_class" in res["reason"]


def test_class_suffixed_issuer_without_any_reference_is_not_trusted():
    universe = [{"name": "Foo B", "ticker": "FOO.B", "raw_provider_fields": {"nasdaq_orderbook_id": "T1"}}]
    fetch = lambda ob, **_: {"shares": 100e6, "market_cap": 1e9, "fetchedAt": "x", "cache": "live"}
    res = nns.resolve_issuer_value(
        name="Foo AB", orderbook_id="T1", country="SE", exchange="NASDAQ_STOCKHOLM",
        reference_shares=None, reference_label=None, universe=universe, fetch=fetch,
    )
    assert res["status"] == "unverified"


def test_unsuffixed_single_listed_line_is_accepted_without_reference():
    universe = [{"name": "AAK", "ticker": "AAK", "raw_provider_fields": {"nasdaq_orderbook_id": "T2"}}]
    fetch = lambda ob, **_: {"shares": 261e6, "market_cap": 48e9, "fetchedAt": "x", "cache": "live"}
    res = nns.resolve_issuer_value(
        name="AAK AB", orderbook_id="T2", country="SE", exchange="NASDAQ_STOCKHOLM",
        reference_shares=None, reference_label=None, universe=universe, fetch=fetch,
    )
    assert res["status"] == "verified" and res["market_cap"] == 48e9


def test_series_summary_failure_leaves_market_cap_missing_with_reason(monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_NORDIC_SERIES", "1")
    monkeypatch.setattr(service, "resolve_issuer_value", lambda **kw: nns.resolve_issuer_value(**kw, universe=UNIVERSE, fetch=lambda *a, **k: None))
    out = service._derive_metrics(volvo_car())
    assert out.market_cap is None
    assert any(n.startswith("market_cap_withheld:series_summary_unavailable") for n in out.raw_provider_fields["derived_metrics"])


# --- exchange market cap seeding -----------------------------------------------------------

def test_official_quote_market_cap_is_seeded_with_basis():
    company = GlobalCompany(country="GB", exchange="LSE", currency="GBP", ticker="SHEL", name="Shell")
    quote = {"provider": "official-lse-main-market-price-explorer", "marketCap": 2.17e11, "marketCapBasis": "exchange_reported_line", "quoteDate": "2026-10-12"}
    cap, fields = market_cap_from_quote(company, quote)
    assert cap == 2.17e11 and fields["market_cap_basis"] == "exchange_reported_line"


@pytest.mark.parametrize("quote", [
    {"provider": "yahoo-public-chart-global", "marketCap": 1e9},
    {"provider": "official-x", "marketCap": 0},
    {"provider": "official-x", "marketCap": 1e9, "marketCapCurrency": "USD"},
    {"provider": "official-x", "marketCap": 1e9, "cache": "stale"},
])
def test_market_cap_not_seeded_from_unofficial_zero_foreign_currency_or_cached_quotes(quote):
    company = GlobalCompany(country="GB", exchange="LSE", currency="GBP", ticker="SHEL", name="Shell")
    assert market_cap_from_quote(company, quote) == (None, {})


def test_market_snapshot_gap_does_not_erase_a_seeded_market_cap(tmp_path):
    seed = GlobalCompany(country="GB", exchange="LSE", currency="GBP", ticker="SHEL", name="Shell", market_cap=2.17e11)
    provider = PersistentMarketProvider(upstream=None, data_dir=str(tmp_path))
    payload = {"market": {"market_cap": None, "price": 38.0}, "fetchedAt": "2026-10-13T00:00:00+00:00", "provider": "t"}
    assert provider._decode(seed, payload, fallback=False).market_cap == 2.17e11


# --- cross-currency listings ---------------------------------------------------------------

class _FakeECB:
    rate_date = "2026-10-12"

    def __init__(self, *a, **k):
        pass

    def rate(self, base, quote):
        assert (base, quote) == ("USD", "GBP")
        return 0.75


def test_usd_reporter_listed_in_gbp_gets_fx_converted_pe_ev_and_book_value(monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_FX_CONVERSION", "1")
    monkeypatch.setattr(service, "ECBReferenceFXProvider", _FakeECB)
    co = GlobalCompany(
        country="GB", exchange="LSE", currency="GBP", ticker="SHEL", name="Shell", price=30.0, reporting_currency="USD",
        eps=4.0, market_cap=200e9, shares_outstanding=6e9, total_equity=180e9, ebitda=60e9, total_debt=50e9,
        cash_and_equivalents=40e9,
    )
    out = service._derive_metrics(co)
    assert out.pe == pytest.approx(30.0 / (4.0 * 0.75))
    assert out.book_value_per_share == pytest.approx(180e9 * 0.75 / 6e9)
    assert out.ev_ebitda == pytest.approx((200e9 + 10e9 * 0.75) / (60e9 * 0.75))
    assert any(n.startswith("fx:USD->GBP") for n in out.raw_provider_fields["derived_metrics"])


def test_cross_currency_metrics_stay_missing_when_no_fx_rate(monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_FX_CONVERSION", "1")
    class Broken(_FakeECB):
        def rate(self, base, quote):
            raise RuntimeError("no rate")

    monkeypatch.setattr(service, "ECBReferenceFXProvider", Broken)
    co = GlobalCompany(country="GB", exchange="LSE", currency="GBP", ticker="X", name="X", price=30.0, reporting_currency="USD", eps=4.0)
    out = service._derive_metrics(co)
    assert out.pe is None
    assert any(n.startswith("fx_unavailable") for n in out.raw_provider_fields["derived_metrics"])


# --- Agent 9 / Agent 10 consistency ----------------------------------------------------------

def test_volvo_agent9_high_risk_is_single_trigger_and_agent10_rating_is_flagged_conflicted():
    co = volvo_car()
    distress = distress_agent(co)
    assert distress.status == "HIGH_RISK" and distress.positive_block  # gate unchanged
    assert distress.severe_triggers == ("ebit_interest_coverage<1.0",)
    assert distress.corroboration == "SINGLE_MODEL_UNCORROBORATED"
    assert distress.interest_coverage == pytest.approx(303 / 1251)
    scoring = score_legal_entity_company(co, distress)
    assert scoring["factors"]["ebitda_interest"]["value"] == pytest.approx(24_248 / 1251, rel=1e-3)
    assert scoring["indicated_rating_sp"].startswith("AA")
    consistency = scoring["rating_consistency"]
    assert consistency["status"] == "CONFLICT" and consistency["rating_reliable"] is False
    assert scoring["headline_rating_status"] == "CONFLICTED_WITH_AGENT9_NOT_FOR_DECISION"


def test_consistent_agents_report_consistent():
    co = volvo_car(operating_income=40_000e6, net_income=20_000e6, eps=3.0, current_assets=250_000e6)
    distress = distress_agent(co)
    assert distress.status == "LOW_RISK"
    assert score_legal_entity_company(co, distress)["rating_consistency"]["status"] == "CONSISTENT"


def test_multi_model_distress_is_labelled_multi_model():
    co = volvo_car(operating_income=-5_000e6, net_income=-30_000e6, total_equity=40_000e6, total_liabilities=333_172e6, retained_earnings=-50_000e6)
    distress = distress_agent(co)
    assert distress.status == "HIGH_RISK" and distress.corroboration == "MULTI_MODEL"


# --- confidence semantics ------------------------------------------------------------------

def test_confidence_breakdown_names_the_limiting_factor_and_states_no_calibration():
    breakdown = service._confidence_breakdown(decision=0.52, evidence=0.9158, overall=0.52 * 0.9158)
    assert breakdown["limitingFactor"] == "decision"
    assert breakdown["overall"]["formula"] == "decision x evidence"
    assert breakdown["governanceThresholds"] == {"accept": 0.55, "escalate": 0.35}
    assert "uncalibrated" in breakdown["calibration"]
    assert service._confidence_breakdown(0.9, 0.5, 0.45)["limitingFactor"] == "evidence"


# --- EBITDA from an impairment-inclusive D&A line ---------------------------------------------

_INCL = "ifrs-full:DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss"


def test_impairment_inclusive_da_gives_a_labelled_ebitda_addback():
    result = ESEFFundamentalsProvider().normalized_fields([
        fact("ifrs-full:ProfitLossFromOperatingActivities", 100, DUR), fact("ifrs-full:Revenue", 1000, DUR), fact(_INCL, -30, DUR),
    ], date(2025, 12, 31))
    meta = result["__normalization_meta__"]
    assert result["ebitda"] == 130
    assert meta["ebitda_includes_impairment_addback"] is True
    assert meta["field_status"]["ebitda"] == "extracted_impairment_inclusive_addback"


def test_pure_da_is_preferred_over_the_impairment_inclusive_line():
    result = ESEFFundamentalsProvider().normalized_fields([
        fact("ifrs-full:ProfitLossFromOperatingActivities", 100, DUR), fact("ifrs-full:Revenue", 1000, DUR),
        fact("ifrs-full:DepreciationAndAmortisationExpense", 20, DUR), fact(_INCL, 30, DUR),
    ], date(2025, 12, 31))
    assert result["ebitda"] == 120
    assert result["__normalization_meta__"]["ebitda_includes_impairment_addback"] is False


@pytest.mark.parametrize("extra", [
    [fact("ifrs-full:AdjustmentsForDepreciationAndAmortisationExpenseAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss", 50, DUR)],  # two lines disagree
    [],  # add-back above 60% of revenue (below)
])
def test_ambiguous_or_implausible_impairment_inclusive_da_is_withheld(extra):
    base = [fact("ifrs-full:ProfitLossFromOperatingActivities", 100, DUR), fact("ifrs-full:Revenue", 1000 if extra else 100, DUR), fact(_INCL, 30 if extra else 90, DUR)]
    result = ESEFFundamentalsProvider().normalized_fields(base + extra, date(2025, 12, 31))
    assert result["ebitda"] is None


# --- Nasdaq Nordic series fetch / cache / warm ------------------------------------------------

class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise nns.requests.HTTPError("boom")

    def json(self):
        return self._payload


_SUMMARY = {"data": {"summaryData": {"shares": {"value": "2,979,524,179"}, "marketCap": {"value": "44,543,886,476"}, "isin": {"value": "SE0021628898"}}}}


def test_series_summary_parses_caches_and_serves_fresh_copy_without_a_second_request(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    calls = []
    getter = lambda *a, **k: calls.append(1) or _Resp(_SUMMARY)
    first = nns.fetch_series_summary("TX4016914", getter=getter)
    again = nns.fetch_series_summary("TX4016914", getter=getter)
    assert first["shares"] == 2_979_524_179 and first["market_cap"] == 44_543_886_476 and first["cache"] == "live"
    assert again["cache"] == "fresh" and len(calls) == 1


def test_series_summary_falls_back_to_a_stale_copy_when_the_source_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    nns.fetch_series_summary("TX1", getter=lambda *a, **k: _Resp(_SUMMARY))
    path = tmp_path / "series-summary" / "SE" / "TX1.json"
    import json as _json
    old = _json.loads(path.read_text())
    old["fetchedAt"] = "2026-10-01T00:00:00+00:00"  # older than the 12h freshness window
    path.write_text(_json.dumps(old))
    got = nns.fetch_series_summary("TX1", getter=lambda *a, **k: _Resp({}, 503))
    assert got["cache"] == "stale" and got["shares"] == 2_979_524_179


def test_series_summary_with_garbage_payload_is_none(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    assert nns.fetch_series_summary("TX9", getter=lambda *a, **k: _Resp({"data": None})) is None


def test_warm_series_cache_stops_requesting_after_its_deadline():
    universe = [{"name": f"Co{i}", "raw_provider_fields": {"nasdaq_orderbook_id": f"T{i}"}} for i in range(5)]
    seen = []
    result = nns.warm_series_cache(universe=universe, workers=1, max_seconds=-1, fetch=lambda ob, **k: seen.append(ob) or {"shares": 1})
    assert seen == [] and result["skipped"] == 5


# --- ADR / share-class basis mismatch -----------------------------------------------------------

class _JpyUsd(_FakeECB):
    def rate(self, base, quote):
        assert (base, quote) == ("JPY", "USD")
        return 0.0067


def test_adr_quote_with_ordinary_share_eps_withholds_per_share_ratios_and_uses_cap_based_pe(monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_FX_CONVERSION", "1")
    monkeypatch.setattr(service, "ECBReferenceFXProvider", _JpyUsd)
    # one ADR = 10 ordinary shares: the quote is per ADR, EPS per ordinary share (JPY)
    adr = GlobalCompany(
        country="US", exchange="NYSE", currency="USD", ticker="TM", name="Toyota", price=200.0, reporting_currency="JPY",
        eps=300.0, net_income=4.5e12, market_cap=270e9, total_equity=40e12,
        raw_provider_fields={"market_cap_basis": "exchange_reported_company_level"},
    )
    out = service._derive_metrics(adr)
    assert out.eps is None and out.book_value_per_share is None
    assert out.pe == pytest.approx(270e9 / (4.5e12 * 0.0067))  # class/ADR-agnostic
    assert any(n.startswith("per_share_basis_mismatch") for n in out.raw_provider_fields["derived_metrics"])


def test_matching_share_basis_keeps_per_share_pe(monkeypatch):
    co = GlobalCompany(
        country="US", exchange="NASDAQ", currency="USD", ticker="GOOGL", name="Alphabet", price=350.0, reporting_currency="USD",
        eps=10.8, net_income=130e9, market_cap=4.3e12,
        raw_provider_fields={"market_cap_basis": "exchange_reported_company_level"},
    )
    out = service._derive_metrics(co)
    assert out.pe == pytest.approx(350.0 / 10.8) and not any(n.startswith("per_share_basis_mismatch") for n in out.raw_provider_fields["derived_metrics"])


def test_elevated_risk_against_a_bbb_grid_rating_is_not_a_conflict():
    from global_markets.models import DistressAssessment

    co = volvo_car()
    elevated = DistressAssessment(status="ELEVATED_RISK", positive_block=False, elevated_triggers=("altman_grey_zone",))
    assert rating_consistency(co, elevated, notch=9, coverage=1.0)["status"] == "CONSISTENT"      # BBB
    assert rating_consistency(co, elevated, notch=5, coverage=1.0)["status"] == "CONFLICT"        # A+
    high = DistressAssessment(status="HIGH_RISK", positive_block=True, severe_triggers=("ebit_interest_coverage<1.0",))
    assert rating_consistency(co, high, notch=10, coverage=1.0)["status"] == "CONFLICT"           # BBB- is still investment grade
    assert rating_consistency(co, high, notch=12, coverage=1.0)["status"] == "CONSISTENT"         # BB+
