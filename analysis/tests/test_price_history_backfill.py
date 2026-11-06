import json
from datetime import datetime, timezone

import pytest

import market_memory as mm
import price_history_backfill as pb


@pytest.fixture(autouse=True)
def memory_db(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_MARKET_MEMORY_DB", str(tmp_path / "mm.db"))


def _day(d, close, yclose=100.0):
    return {"dEven": d, "pClosing": close, "priceYesterday": yclose, "insCode": "1", "qTotTran5J": 10}


def test_rows_use_the_close_and_skip_days_without_a_real_close():
    p = {"closingPriceDaily": [_day(20250601, 110.0), _day(20250602, 0), {"dEven": "bad", "pClosing": 5}]}
    rows = pb.rows_from_payload(p, "فولاد", "1", "TSE")
    assert len(rows) == 1 and rows[0][1] == "2025-06-01" and rows[0][6] == 110.0 and rows[0][7] == pytest.approx(10.0) and "insCode" not in rows[0][10]


def test_store_is_idempotent_and_never_overwrites_live_snapshots():
    mm.save_symbol_snapshot(symbol="فولاد", source="kiasha:tsetmc", payload={"quote": {"last_price": 3000.0}}, observed_at=datetime(2025, 6, 1, 9, tzinfo=timezone.utc))
    p = {"closingPriceDaily": [_day(20250601, 110.0)]}
    pb.store(pb.rows_from_payload(p, "فولاد", "1", "TSE")); pb.store(pb.rows_from_payload(p, "فولاد", "1", "TSE"))
    with mm._connect() as con:
        got = {(r["source"], r["price"]) for r in con.execute("SELECT source,price FROM symbol_snapshots WHERE symbol='فولاد'")}
    assert got == {("kiasha:tsetmc", 3000.0), (pb.SOURCE, 110.0)}


def test_closed_days_are_derived_from_the_data_and_never_filled():
    # Sat 2025-06-07 .. Wed 2025-06-11 trading week; nobody trades Sun-Tue (3 trading weekdays in a row)
    days = [20250607, 20250611, 20250614]
    for sym in ("ا", "ب"):
        rows = pb.rows_from_payload({"closingPriceDaily": [_day(d, 100.0 + i) for i, d in enumerate(days)] * 60}, sym, sym, "TSE")
        pb.store(rows)
    # make the sample big enough
    out = pb.derive_no_trading_days(min_rows_per_symbol=1)
    dates = {o["date"]: o["runLengthDays"] for o in out}
    assert dates["2025-06-08"] == 3 and dates["2025-06-09"] == 3 and dates["2025-06-10"] == 3
    assert "2025-06-13" not in dates and "2025-06-06" not in dates  # Friday/Thursday are not trading days
    with mm._connect() as con:
        assert con.execute("SELECT COUNT(*) FROM symbol_snapshots WHERE observed_date='2025-06-09'").fetchone()[0] == 0


def test_one_failing_instrument_does_not_stop_the_run_and_quiet_window_is_respected():
    def fetch(code, n):
        if code == "bad":
            raise RuntimeError("relay 502")
        return {"closingPriceDaily": [_day(20250601, 110.0)]}
    res = pb.backfill([{"symbol": "x", "code": "bad"}, {"symbol": "y", "code": "ok"}], fetch, interval=0, sleep=lambda s: None, log=lambda m: None)
    assert (res["done"], res["failed"]) == (1, 1)
    assert pb.in_quiet_window(datetime(2026, 11, 6, 23, 0, tzinfo=timezone.utc)) and pb.in_quiet_window(datetime(2026, 11, 6, 1, 30, tzinfo=timezone.utc))
    assert not pb.in_quiet_window(datetime(2026, 11, 6, 13, 0, tzinfo=timezone.utc))


def test_backfill_stops_where_live_snapshots_begin():
    mm.save_symbol_snapshot(symbol="ز", source="kiasha:tsetmc", payload={"quote": {"last_price": 5.0}}, observed_at=datetime(2025, 6, 2, 9, tzinfo=timezone.utc))
    fetch = lambda code, n: {"closingPriceDaily": [_day(20250531, 10.0), _day(20250601, 11.0), _day(20250602, 12.0), _day(20250603, 13.0)]}
    pb.backfill([{"symbol": "ز", "code": "9"}], fetch, interval=0, sleep=lambda s: None, log=lambda m: None)
    with mm._connect() as con:
        days = [r[0] for r in con.execute("SELECT observed_date FROM symbol_snapshots WHERE symbol='ز' AND source=? ORDER BY 1", (pb.SOURCE,))]
    assert days == ["2025-05-31", "2025-06-01"]
