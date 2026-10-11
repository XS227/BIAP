import unittest

from global_markets.credit_scoring import reconcile_agent9_agent10, score_legal_entity_company
from global_markets.distress import distress_agent
from global_markets.models import GlobalCompany


def co(**kw):
    base = dict(country="SE", exchange="STO", currency="SEK", ticker="VOLCAR.B", name="Volvo Cars",
                sector="industrial", operating_income=500.0, ebitda=2500.0, interest_expense=400.0,
                total_debt=9000.0, filing_period_end="2025-12-31")
    base.update(kw)
    return GlobalCompany(**base)


class ReconciliationTests(unittest.TestCase):
    def test_negative_signed_interest_does_not_flip_icr(self):
        pos = distress_agent(co(interest_expense=400.0)).interest_coverage
        neg = distress_agent(co(interest_expense=-400.0)).interest_coverage
        self.assertEqual(pos, neg)
        self.assertGreater(neg, 1.0)

    def test_ebit_vs_ebitda_gap_is_explained_not_hidden(self):
        company = co(operating_income=300.0, ebitda=2500.0)
        d = distress_agent(company)
        self.assertLess(d.interest_coverage, 1.0)
        rec = reconcile_agent9_agent10(company, d)
        self.assertEqual(rec["status"], "REVIEW")
        self.assertEqual(rec["implied_da"], 2200.0)
        self.assertTrue(any("depreciation" in f for f in rec["flags"]))
        self.assertGreater(rec["agent10_ebitda_interest"], 6.0)

    def test_ebitda_below_ebit_flagged(self):
        company = co(operating_income=900.0, ebitda=500.0)
        rec = reconcile_agent9_agent10(company, distress_agent(company))
        self.assertTrue(any("EBITDA < EBIT" in f for f in rec["flags"]))

    def test_missing_interest_is_insufficient_not_zero(self):
        company = co(interest_expense=None)
        rec = reconcile_agent9_agent10(company, distress_agent(company))
        self.assertEqual(rec["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(rec["agent10_ebitda_interest"])

    def test_attached_to_agent10_output_without_rating(self):
        company = co()
        result = score_legal_entity_company(company, distress_agent(company))
        self.assertIn("agent9_reconciliation", result)
        self.assertFalse(result["strict_rating_available"])


if __name__ == "__main__":
    unittest.main()
