"""India NSE Integrated Filing XBRL: annual context selection, identity gates,
bank format, re-issued ISIN serials and rounding-unit errors."""
from __future__ import annotations

from pathlib import Path

import pytest

from global_markets.india_nse_filings import (
    NSEIntegratedFilingFundamentalsProvider,
    metrics,
    parse_integrated_xbrl,
    same_equity_issuer,
    scale_break,
)
from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError

FIXTURE = Path(__file__).parent / "fixtures" / "nse_if_20microns_fy2026_consolidated.xml"
ISIN = "INE144J01027"


def test_parse_real_fy2026_filing_uses_twelve_month_context():
    parsed = parse_integrated_xbrl(FIXTURE.read_bytes())
    assert parsed["isin"] == ISIN and parsed["symbol"] == "20MICRONS"
    assert parsed["scope"] == "consolidated" and parsed["audited"] is True
    assert parsed["periodEnd"] == "2026-03-31"
    values = parsed["values"]
    assert values["RevenueFromOperations"] == 9538326000  # FY (FourD), not Q4 (OneD 2610633000)
    assert values["Assets"] == 7562226000
    out = metrics(values, parsed["scope"])
    assert out["net_income"] == 668256000  # owners of parent
    assert out["free_cash_flow"] == 1035949000 - 263589000


def test_bank_format_metrics():
    values = {"InterestEarned": 3.4e12, "Income": 4.95e12, "ProfitLossForThePeriod": 7.6e11,
              "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates": 7.5e11,
              "Assets": 4.9e13, "Capital": 1.5e10, "ReservesAndSurplus": 5.8e12, "Borrowings": 4.0e12}
    out = metrics(values, "consolidated")
    assert out["revenue"] == 4.95e12 and out["net_income"] == 7.5e11
    assert out["total_equity"] == 1.5e10 + 5.8e12
    assert out["total_liabilities"] == 4.9e13 - (1.5e10 + 5.8e12)


def test_owner_share_tagged_zero_falls_back_to_total_profit():
    out = metrics({"RevenueFromOperations": 100.0, "ProfitOrLossAttributableToOwnersOfParent": 0.0,
                   "ProfitLossForPeriod": 12.0}, "consolidated")
    assert out["net_income"] == 12.0


def test_isin_reissue_and_scale_guards():
    assert same_equity_issuer("INE296A01024", "INE296A01032")
    assert not same_equity_issuer("INE296A01024", "INE297A01032")
    assert not same_equity_issuer("INE296A02024", "INE296A01032")
    assert scale_break(174e9, 17.1e9) == 1
    assert scale_break(125.8e6, 24.6e6) is None
    assert scale_break(10.0, 10.5) is None


class _Provider(NSEIntegratedFilingFundamentalsProvider):
    def __init__(self, rows, parsed):
        super().__init__()
        self.rows, self.parsed_by_url = rows, parsed

    def _listing(self, symbol):
        return self.rows

    def _parsed(self, url):
        return self.parsed_by_url[url]


def _row(seq, qe, scope="Consolidated", audited="Audited"):
    return {"seq_Id": seq, "qe_Date": qe, "consolidated": scope, "audited": audited,
            "type": "Integrated Filing- Financials", "type_Sub": "Original",
            "broadcast_Date": "22-May-2026 17:47:48", "xbrl": f"https://nsearchives.nseindia.com/x/{seq}.xml"}


def _parsed(isin=ISIN, symbol="20MICRONS", period="2026-03-31", revenue=9.5e9, assets=7.5e9, audited=True):
    return {"isin": isin, "symbol": symbol, "scope": "consolidated", "audited": audited, "periodEnd": period,
            "values": {"RevenueFromOperations": revenue, "ProfitLossForPeriod": 6.6e8, "Assets": assets}}


COMPANY = GlobalCompany(country="IN", exchange="NSE", currency="INR", ticker="20MICRONS", name="20 Microns", isin=ISIN)


def test_provider_picks_annual_consolidated_and_previous_year():
    rows = [_row(3, "30-JUN-2026"), _row(2, "31-MAR-2026"), _row(1, "31-MAR-2025")]
    parsed = {rows[0]["xbrl"]: {**_parsed(), "periodEnd": None}, rows[1]["xbrl"]: _parsed(),
              rows[2]["xbrl"]: _parsed(period="2025-03-31", revenue=9.0e9)}
    out = _Provider(rows, parsed).enrich_fundamentals(COMPANY)
    assert out.filing_period_end == "2026-03-31" and out.revenue == 9.5e9
    assert round(out.revenue_yoy_pct, 2) == round((9.5 / 9.0 - 1) * 100, 2)
    assert out.sources[-1].source_type == "official_regulatory_xbrl"


def test_provider_rejects_other_issuer_and_rounding_unit_error():
    rows = [_row(2, "31-MAR-2026"), _row(1, "31-MAR-2025")]
    other = {rows[0]["xbrl"]: _parsed(isin="INE999Z01011"), rows[1]["xbrl"]: _parsed(isin="INE999Z01011")}
    with pytest.raises(GlobalProviderError, match="filing ISIN"):
        _Provider(rows, other).enrich_fundamentals(COMPANY)
    tenfold = {rows[0]["xbrl"]: _parsed(revenue=95e9, assets=75e9),
               rows[1]["xbrl"]: _parsed(period="2025-03-31", revenue=9.4e9, assets=7.4e9)}
    out = _Provider(rows, tenfold).enrich_fundamentals(COMPANY)
    assert out.filing_period_end == "2025-03-31"  # FY2026 rejected, FY2025 used


def test_bse_listing_requires_matching_isin():
    bse = GlobalCompany(country="IN", exchange="BSE", currency="INR", ticker="20MICRONS", name="x", isin="INE111A01011")
    rows = [_row(2, "31-MAR-2026")]
    with pytest.raises(GlobalProviderError, match="filing ISIN"):
        _Provider(rows, {rows[0]["xbrl"]: _parsed()}).enrich_fundamentals(bse)
