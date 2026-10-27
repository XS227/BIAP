"""Financial-sector signals, SEC interim/TTM evidence, governance-vs-data reasons."""
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from global_markets.agents import evidence_agent
from global_markets.core_agents import comparison_agent, fundamental_agent
from global_markets.decision_reasons import split_decision_reasons
from global_markets.evidence_contract import fundamental_evidence_contract
from global_markets.financial_signals import financial_metrics
from global_markets.governance import decision_governance_agent
from global_markets.models import AgentSignal, DistressAssessment, GlobalCompany, SourceEvidence
from global_markets.sec_edgar import SECEdgarFundamentalsProvider
from global_markets.sec_interim import build_interim_evidence

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)
OFFICIAL = SourceEvidence(provider="sec-edgar", source_type="official_regulatory_xbrl",
                          source_id="CIK1", period_end="2025-12-31", quality=1.0)
MARKET = SourceEvidence(provider="market", source_type="market_quote", quality=0.9)
BANK_TAXONOMY = {"oam_credit_extraction": {"revenue_method": "bank_net_interest_and_other_banking_income"}}


def company(**kw):
    base = dict(
        country="IT", exchange="MTA", currency="EUR", ticker="ISP", name="Intesa Sanpaolo",
        price=3.5, price_observed_at="2026-10-14T16:00:00Z", market_cap=62e9, pb=0.95,
        revenue=26e9, net_income=8.7e9, net_margin_pct=33.0, total_assets=900e9,
        total_liabilities=834e9, total_equity=66e9, filing_period_end="2025-12-31",
        filing_observed_at="2026-03-10", sector="Financials", industry="Banks",
        sources=[OFFICIAL, MARKET], raw_provider_fields=dict(BANK_TAXONOMY),
    )
    base.update(kw)
    return GlobalCompany(**base)


def industrial(**kw):
    base = dict(
        country="US", exchange="NASDAQ", currency="USD", ticker="AAPL", name="Apple Inc.",
        price=250.0, price_observed_at="2026-10-14T20:00:00Z", market_cap=3.7e12, pe=31.0,
        revenue=400e9, revenue_yoy_pct=6.0, net_income=100e9, net_margin_pct=25.0,
        net_margin_prev_pct=24.0, total_assets=360e9, total_liabilities=285e9, total_equity=75e9,
        operating_cash_flow=110e9, free_cash_flow=100e9, filing_period_end="2025-09-27",
        sources=[replace(OFFICIAL, period_end="2025-09-27"), MARKET],
    )
    base.update(kw)
    return GlobalCompany(**base)


class FinancialSignalTests(unittest.TestCase):
    def test_isp_like_bank_gets_traceable_ratios(self):
        data = financial_metrics(company(), now=NOW)
        self.assertTrue(data["applicable"])
        m = data["metrics"]
        self.assertAlmostEqual(m["roe"]["value"], 8.7 / 66, places=4)
        self.assertAlmostEqual(m["roa"]["value"], 8.7 / 900, places=4)
        self.assertAlmostEqual(m["equityToAssets"]["value"], 66 / 900, places=4)
        self.assertEqual(data["provenance"]["sourceId"], "CIK1")
        self.assertEqual(data["provenance"]["periodEnd"], "2025-12-31")
        self.assertIn("period-end", m["roe"]["basis"])

    def test_only_one_evidence_unit_added(self):
        with_fin = fundamental_agent(company())
        no_class = fundamental_agent(company(raw_provider_fields={}, sector=None, industry=None))
        self.assertIn("ROE", with_fin.reasoning)
        self.assertNotIn("ROE", no_class.reasoning)
        self.assertAlmostEqual(with_fin.confidence - no_class.confidence, 0.12, places=6)
        self.assertLessEqual(with_fin.confidence, 0.82)

    def test_vendor_label_is_not_a_classification(self):
        c = company(raw_provider_fields={"sector_source": "yahoo"}, sector="Financial Services")
        self.assertIsNone(financial_metrics(c, now=NOW))
        self.assertNotIn("ROE", fundamental_agent(c).reasoning)

    def test_authoritative_sector_reference_is_accepted(self):
        c = company(raw_provider_fields={"sector_source": "euronext-icb"})
        self.assertTrue(financial_metrics(c, now=NOW)["applicable"])

    def test_missing_and_invalid_inputs_are_withheld_not_defaulted(self):
        d = financial_metrics(company(total_equity=None), now=NOW)
        self.assertNotIn("roe", d["metrics"])
        self.assertNotIn("equityToAssets", d["metrics"])
        self.assertIn("roe", d["withheld"])
        self.assertIn("roa", d["metrics"])
        neg = financial_metrics(company(total_equity=-5e9), now=NOW)
        self.assertNotIn("roe", neg["metrics"])
        none = financial_metrics(company(net_income=None, total_equity=None, total_assets=None), now=NOW)
        self.assertEqual(none["metrics"], {})
        self.assertEqual(fundamental_agent(company(net_income=None, total_equity=None, total_assets=None,
                                                  revenue=None, net_margin_pct=None, total_liabilities=None)).confidence, 0.0)

    def test_stale_official_data_produces_no_ratios(self):
        c = company(filing_period_end="2023-12-31", sources=[replace(OFFICIAL, period_end="2023-12-31"), MARKET])
        d = financial_metrics(c, now=NOW)
        self.assertFalse(d["applicable"])
        self.assertEqual(d["metrics"], {})

    def test_non_official_source_produces_no_ratios(self):
        vendor = SourceEvidence(provider="yahoo", source_type="public_vendor_financial_metrics", quality=0.6)
        d = financial_metrics(company(sources=[vendor, MARKET]), now=NOW)
        self.assertFalse(d["applicable"])

    def test_non_financial_issuer_unchanged(self):
        c = industrial()
        self.assertIsNone(financial_metrics(c, now=NOW))
        s = fundamental_agent(c)
        self.assertNotIn("ROE", s.reasoning)
        self.assertIsNone(fundamental_evidence_contract(c, now=NOW)["financialSector"])

    def test_pb_relative_needs_verified_same_sector_benchmark(self):
        bench = {"value": 1.2, "scope": "same_sector_scan_median", "count": 5, "cohort": "x"}
        c = company(pe=None, raw_provider_fields={**BANK_TAXONOMY, "peer_pb_benchmark": bench})
        sig = comparison_agent(c)
        self.assertAlmostEqual(financial_metrics(c, now=NOW)["pbRelative"]["relativePct"], -20.83, places=1)
        self.assertEqual(sig.vote, 0.25)
        self.assertLess(sig.confidence, 0.55)
        for bad in ({**bench, "count": 2}, {**bench, "scope": "same_exchange_scan_median"}):
            c2 = company(pe=None, raw_provider_fields={**BANK_TAXONOMY, "peer_pb_benchmark": bad})
            self.assertIsNone(financial_metrics(c2, now=NOW)["pbRelative"])
            self.assertEqual(comparison_agent(c2).confidence, 0.0)

    def test_pb_fallback_does_not_raise_decision_confidence_when_pe_missing(self):
        from global_markets.service import _weighted_score
        bench = {"value": 1.2, "scope": "same_sector_scan_median", "count": 5, "cohort": "x"}
        c = company(pe=None, raw_provider_fields={**BANK_TAXONOMY, "peer_pb_benchmark": bench})
        pb = comparison_agent(c)
        self.assertEqual(pb.vote, 0.25)  # direction still reported
        self.assertEqual(pb.confidence, 0.0)
        others = [AgentSignal("fundamental", 0.2, 0.6, "x"), AgentSignal("risk", 0.1, 0.5, "x")]
        before = AgentSignal("comparison", 0.0, 0.0, "valid positive P/E unavailable")  # pre-fallback signal
        self.assertEqual(_weighted_score([*others, pb]), _weighted_score([*others, before]))

    def test_pe_comparison_unchanged_when_available(self):
        c = industrial(sector_pe=40.0)
        self.assertEqual(comparison_agent(c).confidence, 0.65)

    def test_accept_threshold_unchanged(self):
        import inspect
        self.assertEqual(inspect.signature(decision_governance_agent).parameters["accept_threshold"].default, 0.55)


def _row(val, end, accn, fp, fy, start=None, form="10-Q", filed=None):
    r = {"val": val, "end": end, "accn": accn, "fp": fp, "fy": fy, "form": form, "filed": filed or end}
    if start:
        r["start"] = start
    return r


def gaap_fixture(*, annual_end="2025-12-31", ytd_start="2026-01-01", with_10q=True):
    rev = [_row(400, annual_end, "K1", "FY", 2025, "2025-01-01", "10-K", "2026-02-01")]
    ni = [_row(100, annual_end, "K1", "FY", 2025, "2025-01-01", "10-K", "2026-02-01")]
    ocf = [_row(120, annual_end, "K1", "FY", 2025, "2025-01-01", "10-K", "2026-02-01")]
    assets = [_row(360, annual_end, "K1", "FY", 2025, None, "10-K", "2026-02-01")]
    if with_10q:
        # Q1 filing (older accession) and Q2 filing (latest) with prior-year comparatives.
        rev += [_row(100, "2026-03-31", "Q1", "Q1", 2026, ytd_start, filed="2026-05-01"),
                _row(90, "2025-03-31", "Q1", "Q1", 2026, "2025-01-01", filed="2026-05-01"),
                _row(220, "2026-06-30", "Q2", "Q2", 2026, ytd_start, filed="2026-08-01"),
                _row(120, "2026-06-30", "Q2", "Q2", 2026, "2026-04-01", filed="2026-08-01"),
                _row(190, "2025-06-30", "Q2", "Q2", 2026, "2025-01-01", filed="2026-08-01")]
        ni += [_row(60, "2026-06-30", "Q2", "Q2", 2026, ytd_start, filed="2026-08-01"),
               _row(33, "2026-06-30", "Q2", "Q2", 2026, "2026-04-01", filed="2026-08-01"),
               _row(50, "2025-06-30", "Q2", "Q2", 2026, "2025-01-01", filed="2026-08-01")]
        ocf += [_row(70, "2026-06-30", "Q2", "Q2", 2026, ytd_start, filed="2026-08-01"),
                _row(60, "2025-06-30", "Q2", "Q2", 2026, "2025-01-01", filed="2026-08-01")]
        assets += [_row(380, "2026-06-30", "Q2", "Q2", 2026, None, filed="2026-08-01")]
    def concept(rows):
        return {"units": {"USD": rows}}
    return {
        "RevenueFromContractWithCustomerExcludingAssessedTax": concept(rev),
        "NetIncomeLoss": concept(ni),
        "NetCashProvidedByUsedInOperatingActivities": concept(ocf),
        "Assets": concept(assets),
    }


ANNUAL = {"revenue": 400.0, "netIncome": 100.0, "operatingCashFlow": 120.0}


class InterimEvidenceTests(unittest.TestCase):
    def test_ttm_uses_ytd_minus_prior_ytd_without_double_counting(self):
        out = build_interim_evidence(gaap_fixture(), "2025-12-31", ANNUAL)
        self.assertEqual(out["label"], "LATEST_INTERIM_10Q_UNAUDITED")
        self.assertEqual(out["periodEnd"], "2026-06-30")
        self.assertEqual(out["accession"], "Q2")
        self.assertEqual(out["ytd"]["values"]["revenue"], 220.0)
        self.assertEqual(out["quarter"]["revenue"], 120.0)
        # 400 + 220 - 190; summing Q1+Q2 quarters on top of YTD would give 520+.
        self.assertEqual(out["ttm"]["values"], {"revenue": 430.0, "netIncome": 110.0, "operatingCashFlow": 130.0})
        self.assertEqual(out["balance"]["totalAssets"]["value"], 380.0)
        self.assertFalse(out["audited"])
        self.assertIn("unchanged", out["scoringUse"])

    def test_discrete_quarter_row_is_not_taken_as_ytd(self):
        g = gaap_fixture()
        # Net income carries only the three-month Q2 fact (no cumulative six-month row) for the latest filing.
        g["NetIncomeLoss"]["units"]["USD"] = [
            r for r in g["NetIncomeLoss"]["units"]["USD"] if not (r["accn"] == "Q2" and r["start"] == "2026-01-01")
        ]
        out = build_interim_evidence(g, "2025-12-31", ANNUAL)
        self.assertNotIn("netIncome", out["ytd"]["values"])
        self.assertEqual(out["quarter"]["netIncome"], 33.0)
        self.assertEqual(out["ytd"]["start"], "2026-01-01")  # not dragged to the quarter's 2026-04-01 start
        self.assertEqual(out["ytd"]["values"]["revenue"], 220.0)
        self.assertIn("netIncome", out["ttm"]["withheld"])
        self.assertEqual(out["ttm"]["values"]["revenue"], 430.0)  # other metrics keep their TTM

    def test_non_adjacent_fiscal_periods_withhold_ttm(self):
        # Latest annual in companyfacts is FY2024; the 10-Q YTD belongs to FY2026.
        out = build_interim_evidence(gaap_fixture(annual_end="2024-12-31"), "2024-12-31", ANNUAL)
        self.assertIsNone(out["ttm"])
        self.assertIn("boundary", out["ttmWithheldReason"])
        self.assertEqual(out["ytd"]["values"]["revenue"], 220.0)

    def test_missing_prior_year_comparative_withholds_that_metric(self):
        g = gaap_fixture()
        g["NetIncomeLoss"]["units"]["USD"] = [r for r in g["NetIncomeLoss"]["units"]["USD"] if r["end"] != "2025-06-30"]
        out = build_interim_evidence(g, "2025-12-31", ANNUAL)
        self.assertNotIn("netIncome", out["ttm"]["values"])
        self.assertIn("netIncome", out["ttm"]["withheld"])
        self.assertEqual(out["ttm"]["values"]["revenue"], 430.0)

    def test_no_newer_10q_means_no_interim_block(self):
        self.assertIsNone(build_interim_evidence(gaap_fixture(with_10q=False), "2025-12-31", ANNUAL))
        self.assertIsNone(build_interim_evidence({}, "2025-12-31", ANNUAL))
        self.assertIsNone(build_interim_evidence(gaap_fixture(), None, ANNUAL))

    def _enrich(self, with_10q):
        provider = SECEdgarFundamentalsProvider(user_agent="test test@example.com")
        payload = {"entityName": "Test Corp", "facts": {"us-gaap": gaap_fixture(with_10q=with_10q)}}
        provider._get_json = lambda url: payload if "companyfacts" in url else {}
        base = GlobalCompany(country="US", exchange="NASDAQ", currency="USD", ticker="TST", name="Test Corp",
                             raw_provider_fields={"sec_cik": 1})
        return provider.enrich_fundamentals(base)

    def test_annual_scoring_inputs_and_gates_identical_with_and_without_10q(self):
        a, b = self._enrich(True), self._enrich(False)
        for field in ("revenue", "net_income", "total_assets", "operating_cash_flow", "filing_period_end"):
            self.assertEqual(getattr(a, field), getattr(b, field), field)
        self.assertEqual(a.revenue, 400.0)
        self.assertIn("sec_interim", a.raw_provider_fields)
        self.assertNotIn("sec_interim", b.raw_provider_fields)
        ca = fundamental_evidence_contract(a, now=NOW)
        cb = fundamental_evidence_contract(b, now=NOW)
        self.assertEqual(ca["freshnessTier"], cb["freshnessTier"])
        self.assertEqual(ca["freshnessTier"], "LAST_ANNUAL_FILING")
        self.assertEqual(ca["values"], cb["values"])
        self.assertEqual(ca["interimEvidence"]["ttm"]["values"]["revenue"], 430.0)
        self.assertIsNone(cb["interimEvidence"])
        self.assertTrue(any("interimEvidence" in line for line in ca["limitations"]))
        ev_a = evidence_agent(a, now=NOW)
        ev_b = evidence_agent(b, now=NOW)
        self.assertEqual((ev_a.status, ev_a.freshness_score), (ev_b.status, ev_b.freshness_score))


def _distress(status="LOW_RISK"):
    return DistressAssessment(status=status, positive_block=False)


class DecisionReasonSplitTests(unittest.TestCase):
    def test_aapl_disagreement_is_governance_not_stale_data(self):
        c = industrial()
        signals = [AgentSignal("fundamental", 0.6, 0.8, "x"), AgentSignal("risk", -0.5, 0.7, "y")]
        ev = evidence_agent(c, signals, now=NOW)
        self.assertEqual(ev.status, "PASS")
        gov = decision_governance_agent(proposed_call="BUY_CANDIDATE", score=0.3, overall_confidence=0.7,
                                        decision_confidence=0.7, evidence=ev, distress=_distress())
        self.assertEqual(gov.action, "REVIEW")
        fe = fundamental_evidence_contract(c, now=NOW)
        self.assertEqual(fe["freshnessTier"], "LAST_ANNUAL_FILING")
        out = split_decision_reasons(governance=gov.__dict__, evidence=ev.__dict__, distress=_distress().__dict__,
                                     fundamental_evidence=fe, confidence=0.7)
        self.assertEqual([g["code"] for g in out["governance"]], ["AGENT_DISAGREEMENT"])
        self.assertTrue(out["governanceDriven"])
        self.assertFalse(out["dataDriven"])
        codes = {d["code"]: d for d in out["dataLimitations"]}
        self.assertIn("LAST_ANNUAL_FILING", codes)
        self.assertFalse(codes["LAST_ANNUAL_FILING"]["blocksDecision"])
        self.assertNotIn("annual", out["governance"][0]["text"].lower())
        self.assertNotIn("disagree", codes["LAST_ANNUAL_FILING"]["text"].lower())

    def test_missing_evidence_is_data_limitation(self):
        c = industrial(sources=[MARKET], filing_period_end=None)
        ev = evidence_agent(c, [], now=NOW)
        self.assertEqual(ev.status, "BLOCK")
        gov = decision_governance_agent(proposed_call="NO_RECOMMENDATION", score=0.0, overall_confidence=0.1,
                                        decision_confidence=0.1, evidence=ev, distress=_distress())
        out = split_decision_reasons(governance=gov.__dict__, evidence=ev.__dict__, distress=_distress().__dict__,
                                     fundamental_evidence=fundamental_evidence_contract(c, now=NOW), confidence=0.1)
        self.assertEqual(out["governance"], [])
        self.assertTrue(out["dataDriven"])
        self.assertEqual(out["dataLimitations"][0]["code"], "EVIDENCE_BLOCK")
        self.assertIn("fundamental_source", out["dataLimitations"][0]["text"])

    def test_stale_filing_blocks_as_data_not_governance(self):
        stale = replace(OFFICIAL, period_end="2023-06-30")
        c = industrial(sources=[stale, MARKET], filing_period_end="2023-06-30")
        ev = evidence_agent(c, [], now=NOW)
        self.assertEqual(ev.status, "BLOCK")
        out = split_decision_reasons(
            governance={"accepted": False, "hard_blocks": ("task/evidence gate is out of scope or blocked",)},
            evidence=ev.__dict__, distress=_distress().__dict__,
            fundamental_evidence=fundamental_evidence_contract(c, now=NOW), confidence=0.2)
        self.assertEqual(out["governance"], [])
        self.assertIn("fresh_fundamentals", out["dataLimitations"][0]["text"])

    def test_both_kinds_stay_separate_when_both_present(self):
        c = industrial(sources=[MARKET], filing_period_end=None)
        signals = [AgentSignal("fundamental", 0.6, 0.8, "x"), AgentSignal("risk", -0.5, 0.7, "y")]
        ev = evidence_agent(c, signals, now=NOW)
        out = split_decision_reasons(governance={"accepted": False}, evidence=ev.__dict__,
                                     distress=_distress().__dict__, fundamental_evidence=None, confidence=0.6)
        self.assertEqual([g["code"] for g in out["governance"]], ["AGENT_DISAGREEMENT"])
        self.assertEqual(out["dataLimitations"][0]["code"], "EVIDENCE_BLOCK")

    def test_accepted_decision_has_no_blocking_reasons(self):
        c = industrial(filing_period_end="2026-06-30", sources=[replace(OFFICIAL, period_end="2026-06-30"), MARKET])
        ev = evidence_agent(c, [], now=NOW)
        fe = fundamental_evidence_contract(c, now=NOW)
        out = split_decision_reasons(governance={"accepted": True}, evidence=ev.__dict__,
                                     distress=_distress().__dict__, fundamental_evidence=fe, confidence=0.7)
        self.assertEqual(out["governance"], [])
        self.assertFalse(out["governanceDriven"])


if __name__ == "__main__":
    unittest.main()
