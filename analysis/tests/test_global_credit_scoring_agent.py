import math
import unittest

from global_markets.credit_scoring import rating_pd, score_individual_credit, score_legal_entity_company
from global_markets.models import DistressAssessment, GlobalCompany


def company(**kw):
    base = dict(
        country="US", exchange="NASDAQ", currency="USD", ticker="TEST", name="Test Corp",
        sector="industrial", ebitda=400.0, total_debt=600.0, interest_expense=40.0,
        free_cash_flow=180.0, current_assets=600.0, current_liabilities=300.0,
        raw_provider_fields={"agent10_ffo": 300.0, "agent10_industry_risk": 3, "agent10_governance": "satisfactory"},
    )
    base.update(kw)
    return GlobalCompany(**base)


class Agent10CreditScoringTests(unittest.TestCase):
    def test_individual_matches_canonical_math(self):
        result = score_individual_credit(
            payment_on_time_ratio=1.0,
            credit_utilization=0.1,
            credit_history_years=15,
            debt_to_income=0.2,
            active_accounts=4,
            bounced_checks=0,
            past_defaults=0,
        )
        z = -4.4 + 1.5 * 0.1 - 0.55 * math.log(16) + 2.0 * 0.2
        self.assertEqual(result["log_odds"], round(z, 3))
        self.assertEqual(result["pd"], round(1 / (1 + math.exp(-z)), 4))
        self.assertEqual(result["risk_band"], "very low")

    def test_corporate_grid_matches_canonical_example(self):
        distress = DistressAssessment(status="LOW_RISK", positive_block=False, distress_probability=0.01, synthetic_credit_band="A")
        result = score_legal_entity_company(company(), distress)
        cats = {k: v["category"] for k, v in result["factors"].items()}
        self.assertEqual(cats["debt_ebitda"], "A")
        self.assertEqual(cats["ebitda_interest"], "A")
        self.assertEqual(cats["ffo_debt"], "A")
        self.assertEqual(cats["liquidity"], "Aa")
        self.assertEqual(cats["industry_risk"], "Baa")
        self.assertEqual(cats["governance"], "A")
        self.assertEqual(result["weight_coverage"], 1.0)
        self.assertTrue(result["report_only"])
        self.assertEqual(result["agent9_crosscheck"]["damodaran_icr_rating"], "A")

    def test_missing_inputs_are_not_guessed(self):
        result = score_legal_entity_company(company(ebitda=None, raw_provider_fields={}), None)
        self.assertIn("insufficient data", result["status"])
        self.assertIn("debt_ebitda", result["factors_missing"])

    def test_rating_pd_monotonic(self):
        values = [rating_pd(n) for n in range(1, 22)]
        self.assertEqual(values, sorted(values))


if __name__ == "__main__":
    unittest.main()
