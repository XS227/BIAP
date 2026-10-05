"""filings.xbrl.org index rows whose period ends after they were filed.

Recordati (LEI 815600FBF92FD3531704) entry 5011 is its FY2022 report indexed
with period_end 2032-12-31; sorted by -period_end it hid the FY2025 report.
"""
import pytest

from global_markets.esef import ESEFFundamentalsProvider
from global_markets.providers import GlobalProviderError

LEI = "815600FBF92FD3531704"


def _row(doc, period, added, country="IT"):
    return {"id": doc, "attributes": {"period_end": period, "date_added": added, "country": country,
                                       "json_url": f"/{LEI}/{period}/{doc}.json", "error_count": 0}}


def _provider(rows):
    provider = ESEFFundamentalsProvider.__new__(ESEFFundamentalsProvider)
    provider._get_json = lambda url, params=None: {"data": rows}
    return provider


def test_misdated_future_period_does_not_outrank_latest_real_filing():
    rows = [
        _row("5011", "2032-12-31", "2023-04-04 21:54:11.951129"),
        _row("24437", "2025-12-31", "2026-04-07 13:18:37.597068"),
        _row("20954", "2024-12-31", "2025-09-24 21:47:27.680191"),
    ]
    assert _provider(rows)._latest_filing(LEI, "IT")["id"] == "24437"


def test_only_misdated_rows_means_no_usable_filing():
    with pytest.raises(GlobalProviderError):
        _provider([_row("5011", "2032-12-31", "2023-04-04")])._latest_filing(LEI, "IT")
