from datetime import datetime, timezone

from price_provenance import build_price_provenance

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def test_pekarman_gap_is_labelled_not_overwritten():
    stored = {"price": 7170, "price_source": "tsetmc", "quote_fetched_at": datetime(2026, 9, 12, 23, 52, tzinfo=timezone.utc).timestamp()}
    memory = {"price": 10270, "source": "kiasha:tsetmc", "observed_at": "2026-11-03T08:36:00+00:00"}
    out = build_price_provenance(stored, memory, [{"observed_at": "2026-10-29T10:00:00+00:00", "price": 9410, "source": "kiasha:tsetmc"}], now=NOW)
    assert out["storedPrice"]["price"] == 7170 and out["storedPrice"]["status"] == "stale"
    assert out["latestObservation"]["price"] == 10270 and out["latestObservation"]["status"] == "fresh"
    assert out["mostRecent"]["label"] == "market_memory_latest"
    assert out["disagreement"]["storedPrice"] == 7170 and out["disagreement"]["newestPrice"] == 10270
    assert stored["price"] == 7170  # input untouched
    assert out["history"][0]["price"] == 9410


def test_missing_data_is_not_invented():
    out = build_price_provenance({}, None, [], now=NOW)
    assert out["storedPrice"]["status"] == "missing" and out["mostRecent"] is None and out["disagreement"] is None


def test_unknown_time_flagged():
    out = build_price_provenance({"price": 100}, None, None, now=NOW)
    assert out["storedPrice"]["status"] == "unknown_time"
