import manual_trade_routes as routes


def test_manual_trade_routes_registered():
    paths = {getattr(route, "path", None) for route in routes.router.routes}
    assert "/manual-trades/{code}" in paths
    assert "/manual-trades" in paths


def test_manual_trade_positions_aggregate_buys_and_sell():
    rows = [
        {"code": "AAA", "symbol": "نماد", "side": "BUY", "quantity": 10, "price": 100.0, "created_at": "2026-09-01T08:00:00+00:00"},
        {"code": "AAA", "symbol": "نماد", "side": "BUY", "quantity": 10, "price": 200.0, "created_at": "2026-09-01T09:00:00+00:00"},
        {"code": "AAA", "symbol": "نماد", "side": "SELL", "quantity": 5, "price": 250.0, "created_at": "2026-09-01T10:00:00+00:00"},
    ]
    [position] = routes._position_payloads(rows)
    assert position["status"] == "OPEN"
    assert position["quantity"] == 15
    assert position["buyPrice"] == 150.0
    assert position["buyNotional"] == 2250.0
    assert position["source"] == "MANUAL_BROKER"
