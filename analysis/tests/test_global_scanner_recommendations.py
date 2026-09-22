from global_markets.scanner import GlobalMarketScanner


def test_recommendations_deduplicate_same_instrument_keep_best_ranked():
    rows = [
        {"country": "US", "exchange": "NASDAQ", "ticker": "CSCO", "call": "BUY_CANDIDATE", "score": 0.8, "confidence": 0.8},
        {"country": "US", "exchange": "NASDAQ", "ticker": "CSCO", "call": "BUY_CANDIDATE", "score": 0.7, "confidence": 0.8},
        {"country": "US", "exchange": "NASDAQ", "ticker": "AAPL", "call": "BUY_CANDIDATE", "score": 0.6, "confidence": 0.9},
        {"country": "US", "exchange": "NASDAQ", "ticker": "MSFT", "call": "NO_RECOMMENDATION", "score": 0.9, "confidence": 0.9},
    ]

    recommendations = GlobalMarketScanner._recommendations(rows, 10)

    assert [row["ticker"] for row in recommendations] == ["CSCO", "AAPL"]
    assert recommendations[0]["score"] == 0.8
