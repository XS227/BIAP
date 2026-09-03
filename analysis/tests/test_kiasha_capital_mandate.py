from datetime import datetime, timezone

import pytest

from kiasha_capital_mandate import KiashaCapitalMandateStore


def test_mandate_reserves_cash_and_isolates_manual_buying(tmp_path):
    store = KiashaCapitalMandateStore(str(tmp_path / "mandate.sqlite3"))
    mandate = store.create_mandate(
        user_id="u1",
        allocated_cash=30_000_000,
        horizon="week",
        paper_cash_balance=100_000_000,
        now=datetime(2026, 9, 4, tzinfo=timezone.utc),
    )
    assert mandate["mandateCash"] == 30_000_000
    assert store.manual_available_cash(user_id="u1", paper_cash_balance=100_000_000) == 70_000_000
    store.assert_manual_buy_allowed(user_id="u1", paper_cash_balance=100_000_000, cost=70_000_000)
    with pytest.raises(ValueError, match="Kiasha-reserved"):
        store.assert_manual_buy_allowed(user_id="u1", paper_cash_balance=100_000_000, cost=70_000_001)


def test_kiasha_fill_accounting_is_separate_and_realized_pnl_is_correct(tmp_path):
    store = KiashaCapitalMandateStore(str(tmp_path / "mandate.sqlite3"))
    store.create_mandate(
        user_id="u1",
        allocated_cash=30_000_000,
        horizon="month",
        paper_cash_balance=100_000_000,
    )

    after_buy = store.record_fill(
        user_id="u1", intent_id="i-buy", side="BUY", code="FOLD", quantity=100, price=100_000
    )
    assert after_buy["mandateCash"] == 20_000_000
    assert after_buy["positions"][0]["quantity"] == 100
    assert after_buy["positions"][0]["avgCost"] == 100_000
    assert after_buy["accountingEquityAtCost"] == 30_000_000

    after_sell = store.record_fill(
        user_id="u1", intent_id="i-sell", side="SELL", code="FOLD", quantity=40, price=120_000
    )
    assert after_sell["mandateCash"] == 24_800_000
    assert after_sell["positions"][0]["quantity"] == 60
    assert after_sell["realizedPnL"] == 800_000
    assert after_sell["accountingEquityAtCost"] == 30_800_000


def test_stopping_blocks_new_buys_but_allows_exit(tmp_path):
    store = KiashaCapitalMandateStore(str(tmp_path / "mandate.sqlite3"))
    store.create_mandate(
        user_id="u1", allocated_cash=10_000_000, horizon="week", paper_cash_balance=20_000_000
    )
    store.record_fill(
        user_id="u1", intent_id="i-buy", side="BUY", code="X", quantity=10, price=100_000
    )
    stopped = store.request_stop(user_id="u1")
    assert stopped["status"] == "STOPPING"

    with pytest.raises(ValueError, match="new BUYs are blocked"):
        store.record_fill(
            user_id="u1", intent_id="i-buy-2", side="BUY", code="Y", quantity=1, price=100_000
        )

    sold = store.record_fill(
        user_id="u1", intent_id="i-sell", side="SELL", code="X", quantity=10, price=90_000
    )
    assert sold["positions"][0]["quantity"] == 0
    completed = store.complete_if_flat(user_id="u1")
    assert completed is not None
    assert completed["status"] == "COMPLETED"
    assert completed["realizedPnL"] == -100_000


def test_cannot_allocate_more_than_current_paper_cash(tmp_path):
    store = KiashaCapitalMandateStore(str(tmp_path / "mandate.sqlite3"))
    with pytest.raises(ValueError, match="exceeds available Paper cash"):
        store.create_mandate(
            user_id="u1", allocated_cash=100_000_001, horizon="week", paper_cash_balance=100_000_000
        )


def test_fill_is_idempotent_by_user_and_intent(tmp_path):
    store = KiashaCapitalMandateStore(str(tmp_path / "mandate.sqlite3"))
    store.create_mandate(
        user_id="u1", allocated_cash=5_000_000, horizon="week", paper_cash_balance=5_000_000
    )
    first = store.record_fill(
        user_id="u1", intent_id="same", side="BUY", code="X", quantity=10, price=100_000
    )
    second = store.record_fill(
        user_id="u1", intent_id="same", side="BUY", code="X", quantity=10, price=100_000
    )
    assert first["mandateCash"] == second["mandateCash"] == 4_000_000
    assert second["positions"][0]["quantity"] == 10
