import sys
from pathlib import Path

import pytest

ANALYSIS_DIR = Path(__file__).resolve().parents[1]
if str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))

from audit_store import AuditStore
from market_data import LiveQuote, MarketDataUnavailable
import paper_equity_snapshot as snap


@pytest.fixture
def store(tmp_path):
    return AuditStore(db_path=str(tmp_path / "audit.sqlite3"))


def _quote(code: str, price: float) -> LiveQuote:
    return LiveQuote(
        code=code,
        name=code,
        last_price=price,
        closing_price=price,
        yesterday_price=price,
        change=0.0,
        change_percent=0.0,
    )


def test_record_paper_equity_snapshot_upserts_same_day(store):
    store.ensure_paper_account(user_id="u1", initial_cash=1_000_000)
    store.record_paper_equity_snapshot(
        user_id="u1", snapshot_date="1405-06-10", cash_balance=500_000, positions_value=400_000, initial_cash=1_000_000
    )
    store.record_paper_equity_snapshot(
        user_id="u1", snapshot_date="1405-06-10", cash_balance=300_000, positions_value=650_000, initial_cash=1_000_000
    )
    rows = store.list_paper_equity_snapshots(user_id="u1")
    assert len(rows) == 1
    assert rows[0]["cashBalance"] == 300_000
    assert rows[0]["totalEquity"] == 950_000


def test_compute_user_equity_prices_open_positions(monkeypatch):
    prices = {"فولاد": 15000.0, "خودرو": 3000.0}
    monkeypatch.setattr(snap, "find_quote", lambda code, **kw: _quote(code, prices[code]))
    account = {
        "cashBalance": 1_000_000,
        "positions": [
            {"code": "فولاد", "quantity": 10, "avgCost": 12000},
            {"code": "خودرو", "quantity": 5, "avgCost": 2500},
        ],
    }
    result = snap.compute_user_equity(account)
    assert result["unpricedCodes"] == []
    assert result["positionsValue"] == pytest.approx(10 * 15000.0 + 5 * 3000.0)


def test_compute_user_equity_never_fabricates_a_missing_price(monkeypatch):
    def fake_find_quote(code, **kw):
        if code == "خودرو":
            raise MarketDataUnavailable("relay down")
        return _quote(code, 15000.0)

    monkeypatch.setattr(snap, "find_quote", fake_find_quote)
    account = {
        "cashBalance": 1_000_000,
        "positions": [
            {"code": "فولاد", "quantity": 10, "avgCost": 12000},
            {"code": "خودرو", "quantity": 5, "avgCost": 2500},
        ],
    }
    result = snap.compute_user_equity(account)
    assert result["positionsValue"] is None
    assert result["unpricedCodes"] == ["خودرو"]


def test_compute_user_equity_zero_positions_is_pure_cash(monkeypatch):
    monkeypatch.setattr(snap, "find_quote", lambda code, **kw: (_ for _ in ()).throw(AssertionError("should not be called")))
    account = {"cashBalance": 750_000, "positions": []}
    result = snap.compute_user_equity(account)
    assert result["positionsValue"] == 0.0
    assert result["unpricedCodes"] == []


def test_record_snapshot_for_all_users_skips_unpriced_and_records_pure_cash(store, monkeypatch):
    store.ensure_paper_account(user_id="priced", initial_cash=1_000_000)
    store.ensure_paper_account(user_id="unpriced", initial_cash=1_000_000)
    store.ensure_paper_account(user_id="cash-only", initial_cash=500_000)
    with store._connect() as conn:
        conn.execute(
            "INSERT INTO paper_positions (user_id, code, quantity, avg_cost, updated_at) VALUES (?,?,?,?,?)",
            ("priced", "فولاد", 10, 12000, "2026-09-01T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO paper_positions (user_id, code, quantity, avg_cost, updated_at) VALUES (?,?,?,?,?)",
            ("unpriced", "خودرو", 5, 2500, "2026-09-01T00:00:00+00:00"),
        )

    def fake_find_quote(code, **kw):
        if code == "فولاد":
            return _quote(code, 15000.0)
        raise MarketDataUnavailable("relay down")

    monkeypatch.setattr(snap, "find_quote", fake_find_quote)
    summary = snap.record_snapshot_for_all_users(store, snapshot_date="1405-06-10")

    assert summary["attempted"] == 3
    assert summary["recorded"] == 2
    assert summary["skipped"] == 1
    assert summary["errors"] == 0

    priced_rows = store.list_paper_equity_snapshots(user_id="priced")
    assert len(priced_rows) == 1
    assert priced_rows[0]["totalEquity"] == pytest.approx(1_000_000 + 10 * 15000.0)

    cash_only_rows = store.list_paper_equity_snapshots(user_id="cash-only")
    assert len(cash_only_rows) == 1
    assert cash_only_rows[0]["totalEquity"] == 500_000

    assert store.list_paper_equity_snapshots(user_id="unpriced") == []


def test_record_snapshot_for_all_users_one_users_error_does_not_block_others(store, monkeypatch):
    store.ensure_paper_account(user_id="ok", initial_cash=1_000_000)
    store.ensure_paper_account(user_id="broken", initial_cash=1_000_000)

    original_get_account = store.get_paper_account

    def flaky_get_account(*, user_id):
        if user_id == "broken":
            raise RuntimeError("simulated DB hiccup")
        return original_get_account(user_id=user_id)

    monkeypatch.setattr(store, "get_paper_account", flaky_get_account)
    summary = snap.record_snapshot_for_all_users(store, snapshot_date="1405-06-10")

    assert summary["recorded"] == 1
    assert summary["errors"] == 1
    assert store.list_paper_equity_snapshots(user_id="ok")[0]["totalEquity"] == 1_000_000
