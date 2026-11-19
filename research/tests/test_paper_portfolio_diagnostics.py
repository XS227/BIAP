"""Offline unit tests: no network, no server, no mutation of frozen portfolio."""
import math
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paper_portfolio_diagnostics as d


class DiagnosticTests(unittest.TestCase):
    def test_median_and_trim(self):
        values = list(range(1, 21))
        self.assertEqual(d.med(values), 10.5)
        self.assertEqual(d.trimmed(values), (10.5, 1))
        self.assertEqual(d.trimmed([1, 2, 3]), (2.0, 0))

    def test_volatility_is_pre_entry_only(self):
        entry = date(2026, 10, 20)
        start = date(2026, 7, 20)
        values = {}
        date_cursor = start
        close = 100.0
        while date_cursor <= entry + timedelta(days=6):
            if date_cursor.weekday() < 5:
                close *= 1.01 if date_cursor < entry else 1.50
                values[date_cursor.isoformat()] = close
            date_cursor += timedelta(days=1)
        vol, n = d.prior_volatility(values, entry, start)
        self.assertGreaterEqual(n, 40)
        self.assertIsNotNone(vol)
        self.assertLess(vol, 0.001)  # excluded post-entry 50% jumps

    def test_marketcap_split_preserves_sides(self):
        rows = [
            {"market": "US:NASDAQ", "side": "BUY", "return": 0.3, "market_cap": 1.0, "cap_point_in_time": True},
            {"market": "US:NASDAQ", "side": "SELL", "return": -0.1, "market_cap": 2.0, "cap_point_in_time": True},
            {"market": "US:NASDAQ", "side": "BUY", "return": 0.2, "market_cap": 3.0, "cap_point_in_time": True},
            {"market": "US:NASDAQ", "side": "SELL", "return": -0.2, "market_cap": 4.0, "cap_point_in_time": True},
        ]
        low, high = d.get_split(rows, "market_cap", "US:NASDAQ")
        self.assertAlmostEqual(low["median_cut"], 2.5)
        self.assertEqual((low["n_buy"], low["n_sell"]), (1, 1))
        self.assertAlmostEqual(low["spread_pct"], 40.0)
        self.assertEqual((high["n_buy"], high["n_sell"]), (1, 1))

    def test_isin_cross_listed_only_same_side(self):
        rows = [
            {"market":"DE:XETRA","ticker":"ABC","side":"BUY","isin":"DE01","entryClose":5},
            {"market":"DE:FRANKFURT","ticker":"ABC","side":"BUY","isin":"DE01","entryClose":5},
            {"market":"DE:FRANKFURT","ticker":"ABC","side":"SELL","isin":"DE01","entryClose":5},
        ]
        dup = d.choose_duplicates(rows, ["DE:XETRA", "DE:FRANKFURT"])
        self.assertEqual(len(dup), 1)
        self.assertIn(id(rows[1]), dup)


if __name__ == "__main__":
    unittest.main()
