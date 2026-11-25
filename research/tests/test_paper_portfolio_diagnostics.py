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

    # ---- extra inference (2026-11-25) ----
    def test_t_pvalues_match_reference(self):
        self.assertAlmostEqual(d.t_two_sided_p(0.0, 10), 1.0, places=9)
        self.assertAlmostEqual(d.t_two_sided_p(2.2281388519649385, 10), 0.05, places=6)
        self.assertAlmostEqual(d.t_two_sided_p(-2.2281388519649385, 10), 0.05, places=6)
        self.assertAlmostEqual(d.t_two_sided_p(12.706204736432095, 1), 0.05, places=6)
        self.assertAlmostEqual(d.t_two_sided_p(2.0, 1000), 0.045770, places=5)

    def test_exact_sign_test(self):
        self.assertAlmostEqual(d.exact_sign_test_p(8, 2), 0.109375)
        self.assertAlmostEqual(d.exact_sign_test_p(12, 0), 2 / 4096)
        self.assertEqual(d.exact_sign_test_p(5, 5), 1.0)
        self.assertIsNone(d.exact_sign_test_p(0, 0))

    def test_venue_tests(self):
        out = d.venue_tests({"A": 0.1, "B": 0.2, "C": -0.05, "D": 0.15, "E": None})
        self.assertEqual((out["n_venues"], out["n_positive"], out["n_negative"]), (4, 3, 1))
        self.assertAlmostEqual(out["sign_test_p_two_sided"], 0.625)
        self.assertEqual(out["df"], 3)
        self.assertIsNotNone(out["t_test_p_two_sided"])

    def _rows(self):
        def row(m, side, sec, ret):
            return {"market": m, "side": side, "sector": sec, "return": ret}
        return [row("X", "BUY", "Tech", 0.10), row("X", "BUY", "Tech", 0.20), row("X", "SELL", "Tech", 0.00),
                row("X", "BUY", "Bank", 0.05), row("X", "SELL", "Bank", 0.01), row("X", "SELL", "Bank", 0.03),
                row("X", "BUY", "Oil", 0.50),                      # one-sided cell: excluded
                row("X", "SELL", "UNKNOWN", 0.9),                  # unknown sector: excluded
                row("Y", "BUY", "Tech", 0.02), row("Y", "SELL", "Tech", 0.04)]

    def test_sector_neutral_spread_hand_computed(self):
        sn = d.sector_neutral_spread(self._rows())
        # cells: X/Tech spread .15 (w=2*1/3), X/Bank .03 (w=2/3), Y/Tech -.02 (w=.5)
        self.assertEqual((sn["n_cells"], sn["n_cells_used"], sn["n_rows_unknown_sector"]), (4, 3, 1))
        w = [2 / 3, 2 / 3, 0.5]
        sp = [0.15, 0.03, -0.02]
        self.assertAlmostEqual(sn["weighted_spread"], sum(a * b for a, b in zip(w, sp)) / sum(w))
        self.assertAlmostEqual(sn["equal_cell_spread"], sum(sp) / 3)

    def test_bootstrap_is_deterministic_and_brackets_point(self):
        rows = self._rows() * 5
        a = d.stratified_bootstrap(rows, B=500, seed=1)
        b = d.stratified_bootstrap(rows, B=500, seed=1)
        self.assertEqual(a, b)
        for k in ("pooled", "equal_market", "sector_neutral"):
            self.assertLessEqual(a[k]["ci_low_pct"], a[k]["ci_high_pct"])
        self.assertNotEqual(a, d.stratified_bootstrap(rows, B=500, seed=2))

    def test_marketcap_proxy_label(self):
        rows = [{"market": "M", "side": s, "return": r, "market_cap": c, "cap_point_in_time": False}
                for s, r, c in (("BUY", .1, 1.0), ("SELL", 0, 2.0), ("BUY", .2, 3.0), ("SELL", .1, 4.0))]
        for res in d.get_split(rows, "market_cap", "M"):
            self.assertIn("POST_EVENT_PROXY", res["status"])


if __name__ == "__main__":
    unittest.main()
