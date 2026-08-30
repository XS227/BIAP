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
