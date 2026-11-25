"""Decision Accuracy Agent: offline unit tests (reads the packaged v1 cohort file, nothing else, writes nothing)."""
import copy
import inspect
import json
from datetime import date

import pytest
from fastapi import HTTPException

from global_markets import decision_accuracy as da


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv(da.FLAG, raising=False)
    monkeypatch.delenv(da.DATA_DIR_ENV, raising=False)


def mini(decisions, bench, horizon="1", date_="2026-10-20"):
    return {"cohortId": "t", "decisionDate": date_, "decisionLogicVersion": "v1", "benchmarks": {horizon: bench}, "decisions": decisions}


def dec(market, side, ticker, ret, h="1"):
    c, e = market.split(":")
    return {"country": c, "exchange": e, "market": market, "ticker": ticker, "side": side, "tier": side, "score": 0.5,
            "outcomes": {h: {"status": "PRICED", "return": ret, "exitDate": "2026-11-19"}}}


def test_flag_default_off_and_routes_404(monkeypatch):
    import global_routes
    assert da.enabled() is False
    with pytest.raises(HTTPException) as e1:
        global_routes.global_accuracy_summary()
    with pytest.raises(HTTPException) as e2:
        global_routes.global_accuracy_stock("US", "NASDAQ", "MU")
    assert e1.value.status_code == e2.value.status_code == 404
    assert global_routes.global_status()["decisionAccuracyEnabled"] is False
    monkeypatch.setenv(da.FLAG, "1")
    assert global_routes.global_status()["decisionAccuracyEnabled"] is True
    assert global_routes.global_accuracy_summary(horizon=1)["horizon"]["status"] == "MATURED"
    with pytest.raises(HTTPException) as e3:
        global_routes.global_accuracy_summary(horizon=2)
    assert e3.value.status_code == 422


def test_hit_and_excess_definitions():
    assert da.is_hit("BUY", 0.02, 0.01) and not da.is_hit("BUY", 0.00, 0.01)
    assert da.is_hit("SELL", -0.05, -0.02) and not da.is_hit("SELL", 0.01, -0.02)
    assert not da.is_hit("BUY", 0.01, 0.01) and not da.is_hit("SELL", 0.01, 0.01)       # ties are not hits
    assert da.excess_return(0.03, 0.01) == pytest.approx(0.02)


def test_add_months_and_maturity():
    assert da.add_months(date(2026, 10, 20), 1) == date(2026, 11, 20)
    assert da.add_months(date(2026, 10, 20), 12) == date(2027, 10, 20)
    assert da.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert da.matures_on("2026-10-20", 3) == date(2027, 1, 20)


def test_wilson_interval():
    lo, hi = da.wilson(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-3) and hi == pytest.approx(0.5962, abs=1e-3)
    assert da.wilson(0, 0) is None
    lo, hi = da.wilson(10, 10)
    assert hi == pytest.approx(1.0) and lo < 1.0


def test_summary_hand_values_and_pending():
    ds = [dec("US:NASDAQ", "BUY", "A", 0.10), dec("US:NASDAQ", "BUY", "B", -0.02), dec("US:NASDAQ", "SELL", "C", -0.10), dec("US:NASDAQ", "SELL", "D", 0.03)]
    c = mini(ds, {"US:NASDAQ": {"symbol": "^IXIC", "returnPct": 1.0, "exitDate": "2026-11-19"}})
    cfg = {"min_priced_per_side": 10, "bootstrap_resamples": 500, "bootstrap_seed": 1, "confidence_level": 0.95}
    s = da.summarize(c, 1, config=cfg, today=date(2026, 12, 1))
    m = s["markets"]["US:NASDAQ"]
    assert m["buy"]["n"] == 2 and m["buy"]["meanReturnPct"] == pytest.approx(4.0) and m["buy"]["hitRate"] == 0.5
    assert m["sell"]["meanReturnPct"] == pytest.approx(-3.5) and m["sell"]["hitRate"] == 0.5
    assert m["spreadMeanPp"] == pytest.approx(7.5) and m["tooSmallToInterpret"] is True
    assert m["buy"]["meanExcessPct"] == pytest.approx(3.0)
    pooled = s["pooled"]
    lo, hi = pooled["spreadCi95Pp"]
    assert lo <= pooled["spreadMeanPp"] <= hi
    again = da.summarize(c, 1, config=cfg, today=date(2026, 12, 1))["pooled"]["spreadCi95Pp"]
    assert again == pooled["spreadCi95Pp"]                                          # reproducible with the seed
    p3 = da.summarize(c, 3, config=cfg, today=date(2026, 12, 1))
    assert p3["horizon"]["status"] == "PENDING" and p3["horizon"]["matures"] == "2027-01-20" and p3["markets"] is None


def test_unpriced_rows_are_not_counted_and_not_invented():
    d = dec("US:NASDAQ", "BUY", "A", 0.1)
    x = dec("US:NASDAQ", "BUY", "X", 0.0)
    x["outcomes"]["1"] = {"status": "EXCLUDED", "reason": "no_exit_price"}
    c = mini([d, x], {"US:NASDAQ": {"symbol": "^IXIC", "returnPct": 0.0, "exitDate": "2026-11-19"}})
    s = da.summarize(c, 1, config={"min_priced_per_side": 1, "bootstrap_resamples": 10, "bootstrap_seed": 1, "confidence_level": 0.95})
    assert s["markets"]["US:NASDAQ"]["buy"]["n"] == 1
    st = da.stock_record([c], "US", "NASDAQ", "X", config={"horizons_months": [1, 3]})
    assert st["decisions"][0]["horizons"]["1"] == {"status": "NOT_PRICED", "reason": "no_exit_price"}
    assert st["decisions"][0]["horizons"]["3"]["status"] in ("PENDING", "NOT_COMPUTED")


# --- the packaged v1 cohort ---------------------------------------------------------------------------------------------------
def test_v1_cohort_is_bound_to_the_frozen_snapshot_and_verified():
    c = da.load_cohort("v1-20261020")
    assert c["source"]["frozenSnapshotSha256"] == "0bd9066eb980d9293566c2cb682dce579f6d6fbf15e102eeb341e2e7e52621a1"
    assert c["decisionLogicVersion"] == "v1" and len(c["decisions"]) == 964
    assert sum(1 for d in c["decisions"] if d["side"] == "BUY") == 445 and sum(1 for d in c["decisions"] if d["side"] == "SELL") == 519


def test_tampered_cohort_is_rejected(tmp_path, monkeypatch):
    src = da.DATA_DIR
    (tmp_path / "config.json").write_text((src / "config.json").read_text())
    data = json.loads((src / "v1-20261020.json").read_text())
    data["decisions"][0]["outcomes"]["1"]["return"] = 9.99
    (tmp_path / "v1-20261020.json").write_text(json.dumps(data))
    monkeypatch.setenv(da.DATA_DIR_ENV, str(tmp_path))
    with pytest.raises(ValueError):
        da.load_cohort("v1-20261020")


def test_v1_numbers_equal_the_published_diagnostics():
    s = da.summarize(da.load_cohort("v1-20261020"), 1)
    us = s["markets"]["US:NASDAQ"]
    assert (us["buy"]["n"], us["sell"]["n"]) == (151, 212)
    assert us["buy"]["meanReturnPct"] == pytest.approx(-7.00539, abs=1e-4) and us["sell"]["meanReturnPct"] == pytest.approx(-21.23196, abs=1e-4)
    assert us["benchmark"]["returnPct"] == pytest.approx(-9.63345, abs=1e-5)
    nyse = s["markets"]["US:NYSE"]
    assert (nyse["buy"]["n"], nyse["sell"]["n"]) == (118, 66)
    assert nyse["buy"]["meanReturnPct"] == pytest.approx(-3.0527, abs=1e-4) and nyse["sell"]["meanReturnPct"] == pytest.approx(-14.10481, abs=1e-4)
    assert len(s["markets"]) == 12
    assert any(m["tooSmallToInterpret"] for m in s["markets"].values())


def test_primary_pooled_figure_is_venue_equal_and_matches_the_paper():
    s = da.summarize(da.load_cohort("v1-20261020"), 1)
    p, q = s["pooled"], s["pooledStockWeighted"]
    assert "venue-equal" in p["weighting"] and "stock-weighted" in q["weighting"]
    assert p["buy"]["meanReturnPct"] == pytest.approx(-0.35438, abs=1e-4)             # paper / Actions run 44705776623
    assert p["sell"]["meanReturnPct"] == pytest.approx(-10.92912, abs=1e-4)
    assert p["spreadMeanPp"] == pytest.approx(10.575, abs=1e-3)
    assert (q["buy"]["n"], q["sell"]["n"]) == (429, 489)
    assert q["buy"]["meanReturnPct"] == pytest.approx(-3.19366, abs=1e-4) and q["sell"]["meanReturnPct"] == pytest.approx(-14.93223, abs=1e-4)
    assert q["spreadMeanPp"] == pytest.approx(11.739, abs=1e-3)
    assert p["spreadCi95Pp"][0] < p["spreadMeanPp"] < p["spreadCi95Pp"][1]
    assert not any("not evidence of skill" in c for c in s["caveats"])
    assert da.POSITIVE_RANKING_WORDING in s["caveats"]


def test_venue_equal_differs_from_stock_weighted_when_venues_differ_in_size():
    ds = [dec("A:X", "BUY", "a", 0.10), dec("B:Y", "BUY", "b", 0.00), dec("B:Y", "BUY", "c", 0.00), dec("B:Y", "BUY", "d", 0.00),
          dec("A:X", "SELL", "e", -0.10), dec("B:Y", "SELL", "f", 0.00)]
    c = mini(ds, {"A:X": {"symbol": "i", "returnPct": 0.0, "exitDate": "2026-11-19"}, "B:Y": {"symbol": "j", "returnPct": 0.0, "exitDate": "2026-11-19"}})
    s = da.summarize(c, 1, config={"min_priced_per_side": 1, "bootstrap_resamples": 50, "bootstrap_seed": 1, "confidence_level": 0.95})
    assert s["pooled"]["buy"]["meanReturnPct"] == pytest.approx(5.0)                  # (10 + 0) / 2 venues
    assert s["pooledStockWeighted"]["buy"]["meanReturnPct"] == pytest.approx(2.5)     # (10+0+0+0)/4 holdings


def test_v1_later_horizons_are_pending_with_dates():
    c = da.load_cohort("v1-20261020")
    for h, due in ((3, "2027-01-20"), (6, "2027-04-20"), (12, "2027-10-20")):
        s = da.summarize(c, h, today=date(2026, 11, 25))
        assert s["horizon"] == {"status": "PENDING", "matures": due, "note": None} and s["markets"] is None


def test_stock_record_for_a_v1_holding():
    st = da.stock_record(da.load_all(), "US", "NASDAQ", "MU", today=date(2026, 11, 25))
    assert st["n"] == 1
    d = st["decisions"][0]
    assert d["side"] == "BUY" and d["decisionLogicVersion"] == "v1" and d["horizons"]["1"]["status"] == "MATURED"
    assert d["horizons"]["1"]["returnPct"] == pytest.approx(-22.947984, abs=1e-4) and d["horizons"]["12"]["status"] == "PENDING"
    assert da.stock_record(da.load_all(), "US", "NASDAQ", "ZZZZ")["n"] == 0


def test_agent_is_read_only_and_never_touches_the_frozen_file():
    src = inspect.getsource(da)
    for forbidden in ("write_text", "write_bytes", "open(", "os.remove", "unlink", "paper_portfolio_2026"):
        assert forbidden not in src
    c = da.load_cohort("v1-20261020")
    before = copy.deepcopy(c)
    da.summarize(c, 1)
    assert c == before
    import global_markets.decision_logic as dl
    assert "decision_accuracy" not in inspect.getsource(dl)


def test_list_decisions_matches_summary_and_pages(monkeypatch):
    c = da.load_cohort("v1-20261020")
    today = date(2026, 11, 25)
    s = da.summarize(c, 1, today=today)
    n_priced = sum(m["buy"]["n"] + m["sell"]["n"] for m in s["markets"].values())
    out = da.list_decisions(c, 1, limit=5, today=today)
    assert out["total"] == n_priced == 918 and len(out["rows"]) == 5
    ed = [r["edgePct"] for r in out["rows"]]
    assert ed == sorted(ed, reverse=True)                                      # default sort: best call first (direction-adjusted)
    assert all(r["edgePct"] == pytest.approx(r["excessPct"] if r["side"] == "BUY" else -r["excessPct"]) for r in out["rows"])
    assert out["rows"][0]["hit"] is True                                       # the best calls are hits, not SELLs that rose
    worst = da.list_decisions(c, 1, sort="edge_asc", limit=3, today=today)["rows"]
    assert all(r["hit"] is False for r in worst)
    raw = [r["excessPct"] for r in da.list_decisions(c, 1, sort="excess_desc", limit=5, today=today)["rows"]]
    assert raw == sorted(raw, reverse=True)
    page2 = da.list_decisions(c, 1, limit=5, offset=5, today=today)["rows"]
    assert len(page2) == 5 and {r["ticker"] for r in page2}.isdisjoint({r["ticker"] for r in out["rows"]})
    assert da.list_decisions(c, 1, limit=500, today=today)["limit"] == 200
    buys = da.list_decisions(c, 1, side="buy", limit=200, today=today)
    assert buys["total"] == sum(m["buy"]["n"] for m in s["markets"].values()) and all(r["side"] == "BUY" for r in buys["rows"])
    mu = da.list_decisions(c, 1, q="micron", today=today)
    assert any(r["ticker"] == "MU" for r in mu["rows"])
    one = da.list_decisions(c, 1, market="ES:BME_MADRID", today=today)
    assert one["total"] == 12 and all(r["market"] == "ES:BME_MADRID" for r in one["rows"])


def test_list_decisions_pending_and_bad_sort_and_route_flag(monkeypatch):
    import global_routes
    c = da.load_cohort("v1-20261020")
    p = da.list_decisions(c, 3, today=date(2026, 11, 25))
    assert p["rows"] == [] and p["total"] == 0 and "2027-01-20" in p["message"]
    with pytest.raises(ValueError):
        da.list_decisions(c, 1, sort="nope", today=date(2026, 11, 25))
    with pytest.raises(HTTPException) as e:
        global_routes.global_accuracy_decisions()
    assert e.value.status_code == 404
    monkeypatch.setenv(da.FLAG, "1")
    assert global_routes.global_accuracy_decisions(horizon=1, limit=3)["rows"]
    with pytest.raises(HTTPException) as e2:
        global_routes.global_accuracy_decisions(horizon=1, side="HOLD")
    assert e2.value.status_code == 422


def test_caveat_states_total_return_basis():
    s = da.summarize(da.load_cohort("v1-20261020"), 1, today=date(2026, 11, 25))
    assert not any("no dividends" in c for c in s["caveats"]) and any("total return" in c for c in s["caveats"])
