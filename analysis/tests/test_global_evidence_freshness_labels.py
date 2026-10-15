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


class PriceVsFundamentalFreshnessTests(unittest.TestCase):
    CASES = [  # (country, exchange, ticker, currency, period_end, expected tier)
        ("US", "NASDAQ", "TSLA", "USD", "2025-12-31", "LAST_ANNUAL_FILING"),
        ("US", "NYSE", "TSLX", "USD", "2026-06-30", "RECENT_ANNUAL_FILING"),
        ("GB", "LSE", "SHEL", "GBP", "2025-12-31", "LAST_ANNUAL_FILING"),
        ("FR", "EURONEXT_PARIS", "MC", "EUR", "2026-06-30", "RECENT_ANNUAL_FILING"),
        ("IT", "BORSA_ITALIANA", "ENEL", "EUR", "2025-12-31", "LAST_ANNUAL_FILING"),
        ("SE", "NASDAQ_STOCKHOLM", "VOLV-B", "SEK", "2025-12-31", "LAST_ANNUAL_FILING"),
        ("NO", "OSLO_BORS", "EQNR", "NOK", "2026-06-30", "RECENT_ANNUAL_FILING"),
    ]

    def test_tier_and_period_date_per_market_and_price_is_independent(self):
        for country, exchange, ticker, ccy, period, tier in self.CASES:
            with self.subTest(ticker=ticker):
                c = tsla(country=country, exchange=exchange, ticker=ticker, currency=ccy,
                         filing_period_end=period, price=10.0, price_observed_at="2026-10-09T16:30:00Z",
                         sources=[SourceEvidence(provider="official", source_type="official_filing_xbrl",
                                                 period_end=period, provenance_status="official")])
                ev = fundamental_evidence_contract(c, now=NOW)
                self.assertEqual(ev["freshnessTier"], tier)
                d = ev["freshnessDetail"]
                self.assertEqual(d["latestOfficialPeriodEnd"], period)
                self.assertEqual(d["priceAgeDays"], 2)  # price age never borrows the filing age
                self.assertNotEqual(d["priceAgeDays"], d["periodAgeDays"])
                self.assertEqual(ev["officialStatus"], "OFFICIAL_CURRENT")  # source verification stays separate

    def test_fresh_price_does_not_make_old_fundamentals_recent(self):
        c = tsla(price_observed_at="2026-10-11T00:00:00Z")
        self.assertEqual(fundamental_evidence_contract(c, now=NOW)["freshnessTier"], "LAST_ANNUAL_FILING")

    def test_unofficial_fundamentals_are_not_current(self):
        c = tsla(sources=[])
        ev = fundamental_evidence_contract(c, now=NOW)
        self.assertEqual(ev["freshnessTier"], "NOT_CURRENT")
