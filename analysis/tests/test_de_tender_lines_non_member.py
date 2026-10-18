"""DE tendered-share lines ("Z.VERK.", e.g. Ceconomy DE000A40ZVV0) carry no fundamentals, hence no P/E or P/B: they are
non-members of the benchmark and must stay out of both the numerator and the denominator of the filing gate."""
from datetime import date

from global_markets import freshness as fr


def _row(ticker, pe=None, pb=None, period=None):
    return {"company": {"ticker": ticker, "pe": pe, "pb": pb, "filing_period_end": period}}


def test_tender_lines_do_not_change_the_gate_denominator():
    peers = [_row("AAA", 10, 1, "2026-12-31"), _row("BBB", 12, 1.2, None)]
    tender = [_row("CECV"), _row("NA9A"), _row("CBK0"), _row("DHE1")]     # no pe/pb, no filing date
    today = date(2026, 10, 16)
    base = fr.filing_dimension(peers, "DE", today)
    with_lines = fr.filing_dimension(peers + tender, "DE", today)
    assert base["excludedCount"] == with_lines["excludedCount"] == 1
    assert base["excludedPct"] == with_lines["excludedPct"] == 50.0
    assert set(with_lines["excluded"]) == {"BBB"}
