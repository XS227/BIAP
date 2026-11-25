from tsetmc_enrichment import _client_flow, _history_performance


def test_history_performance_builds_multi_horizon_returns():
    rows = [{"dEven": 20250101 + i, "pClosing": 100 + i} for i in range(300)]
    perf = _history_performance(rows)
    assert perf["return_1w"] is not None
    assert perf["return_1m"] is not None
    assert perf["return_3m"] is not None
    assert perf["return_1y"] is not None
    assert perf["volatility"] is not None
    assert perf["source"] == "tsetmc-history"


def test_client_flow_uses_verified_individual_fields():
    flow = _client_flow({
        "buy_I_Value": 1500,
        "sell_I_Value": 1000,
        "buy_N_Value": 500,
        "sell_N_Value": 1000,
        "buy_I_Volume": 300,
        "sell_I_Volume": 200,
        "buy_CountI": 3,
        "sell_CountI": 4,
    })
    assert flow["retail_net"] == 500
    assert flow["institutional_net"] == -500
    assert flow["buy_per_capita"] == 100
    assert flow["sell_per_capita"] == 50


def test_untraded_base_price_rows_and_discontinuities_do_not_create_fake_returns():
    from tsetmc_enrichment import _history_performance
    rows = [{"dEven": 20260701 + i, "pClosing": 1000.0, "priceFirst": 0.0} for i in range(40)]
    rows += [{"dEven": 20260801 + i, "pClosing": 12800.0 * (1.01 ** i), "priceFirst": 12800.0} for i in range(30)]
    perf = _history_performance(rows)
    assert perf["return_3m"] is None and perf["return_1y"] is None
    assert perf["volatility"] is None or perf["volatility"] < 100
    # an unadjusted jump mid-series restarts the series
    rows2 = [{"dEven": 20260101 + i, "pClosing": 100.0, "priceFirst": 100.0} for i in range(30)]
    rows2 += [{"dEven": 20260201 + i, "pClosing": 500.0, "priceFirst": 500.0} for i in range(30)]
    perf2 = _history_performance(rows2)
    assert perf2["return_1m"] == 0.0 and perf2["return_3m"] is None
