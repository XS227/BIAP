import unittest
from datetime import datetime, timezone

from global_markets.evidence_contract import fundamental_evidence_contract
from global_markets.models import GlobalCompany, SourceEvidence


def tsla(**kw):
    base = dict(
        country="US", exchange="NASDAQ", currency="USD", ticker="TSLA", name="Tesla, Inc.",
        revenue=94.8e9, net_income=7.1e9, filing_period_end="2025-12-31",
        sources=[SourceEvidence(provider="sec-edgar", source_type="official_filing_xbrl",
                                period_end="2025-12-31", provenance_status="official")],
    )
    base.update(kw)
    return GlobalCompany(**base)


NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


class FreshnessLabelTests(unittest.TestCase):
    def test_284_day_old_annual_is_last_annual_not_fresh(self):
        c = fundamental_evidence_contract(tsla(), now=NOW)
        self.assertEqual(c["officialStatus"], "OFFICIAL_CURRENT")
        self.assertEqual(c["fundamentalPeriodAgeDays"], 284)
        self.assertEqual(c["freshnessTier"], "LAST_ANNUAL_FILING")
        self.assertTrue(any("last annual filing only" in x for x in c["limitations"]))

    def test_missing_icr_inputs_are_disclosed(self):
        c = fundamental_evidence_contract(tsla(), now=NOW)
        self.assertTrue(any("interest coverage unavailable" in x for x in c["limitations"]))

    def test_recent_annual_has_no_age_limitation(self):
        c = fundamental_evidence_contract(
            tsla(filing_period_end="2026-06-30", interest_expense=1.0, operating_income=2.0, ebitda=3.0), now=NOW)
        self.assertEqual(c["freshnessTier"], "RECENT_ANNUAL_FILING")
        self.assertEqual(c["limitations"], [])


if __name__ == "__main__":
    unittest.main()
