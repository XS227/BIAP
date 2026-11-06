"""Regression + independent numeric validation for the Iran module repair (digits, verification, EDA scope, KPI, re-parse)."""
import math

import pytest

import module_compute as mc
import module_dataset as md
import module_stats as st
from codal_reparse import verify_statement


def _codal(i, **over):
    base = {"revenue_current": 1000.0 + i * 10, "revenue_prev": 800.0, "net_profit_current": 100.0 + i, "net_profit_prev": 80.0,
            "total_assets_current": 2000.0, "total_assets_prev": 1800.0, "total_liabilities_current": 1200.0, "total_liabilities_prev": 1100.0,
            "total_equity_current": 800.0, "total_equity_prev": 700.0, "current_assets_current": 900.0, "current_liabilities_current": 600.0,
            "operating_cash_flow_current": 150.0, "report_scope": "consolidated", "tracing_no": str(1000 + i),
            "report_title": "صورت‌های مالی سال مالی منتهی به ۱۴۰۴/۱۲/۲۹ (حسابرسی شده)"}
    base.update(over)
    return base


def _item(code, codal=None, market=None):
    company = {}
    if codal is not None:
        company["codal"] = codal
    if market is not None:
        company["market"] = market
    return {"code": code, "symbol": code, "name": code, "market": "بورس", "enrichedAt": None, "company": company or None}


def _universe(n=12):
    return [dict(md.universe_row(_item(f"S{i}", _codal(i), {"last_price": 1000 + i, "pe": 5.0 + i, "market_cap": 1e9 * (i + 1)})), is_primary=1, category="operating_company")
            for i in range(n)]


# ---- identity -------------------------------------------------------------------------------

def test_persian_arabic_and_latin_digits_are_the_same_instrument():
    keys = {md.symbol_key(x) for x in ("شاوان۳", "شاوان٣", "شاوان3", "شاوان ۳")}
    assert keys == {"شاوان3"}


# ---- statement verification (independent balance identity) -----------------------------------

def test_balanced_statement_is_verified_and_unbalanced_is_unverified():
    ok = md.build_company_dataset(_item("A", _codal(0)))
    assert ok["fundamentals"]["verification"]["status"] == "verified"
    assert ok["ratios"]["roa"]["value"] == 100.0 / 2000.0
    bad = md.build_company_dataset(_item("B", _codal(0, total_assets_current=843393.0, total_equity_current=24826686.0, total_liabilities_current=141311.0)))
    assert bad["fundamentals"]["verification"]["status"] == "unverified"
    assert any("تراز نیست" in r for r in bad["fundamentals"]["verification"]["reasons"])
    # balance-sheet ratios are withheld with a reason; income-statement ratios are kept
    for key in md.BALANCE_SHEET_RATIOS:
        assert bad["ratios"][key]["value"] is None
    assert bad["ratios"]["roe"]["unverified"] is True and "تأییدنشده" in bad["ratios"]["roe"]["reason"]
    assert bad["ratios"]["net_margin"]["value"] == 100.0 / 1000.0
    assert any("withheld" in w for w in bad["quality"]["warnings"])


def test_missing_balance_inputs_are_incomplete_not_verified():
    ds = md.build_company_dataset(_item("C", _codal(0, total_liabilities_current=None)))
    assert ds["fundamentals"]["verification"]["status"] == "incomplete"
    assert ds["ratios"]["debt_ratio"]["value"] is None


def test_ratios_match_independent_recomputation():
    c = _codal(3)
    r = md.build_company_dataset(_item("D", c))["ratios"]
    assert math.isclose(r["net_margin"]["value"], c["net_profit_current"] / c["revenue_current"])
    assert math.isclose(r["roe"]["value"], c["net_profit_current"] / c["total_equity_current"])
    assert math.isclose(r["debt_ratio"]["value"], c["total_liabilities_current"] / c["total_assets_current"])
    assert math.isclose(r["current_ratio"]["value"], 900.0 / 600.0)
    assert math.isclose(r["revenue_growth"]["value"], (c["revenue_current"] - 800.0) / 800.0)
    assert math.isclose(r["cfo_to_profit"]["value"], 150.0 / c["net_profit_current"])


# ---- re-verification against the original filing --------------------------------------------

def _html(rows):
    return "<html><body><table>" + "".join("<tr><td>" + "</td><td>".join(str(c) for c in row) + "</td></tr>" for row in rows) + "</table></body></html>"


def test_reparse_corrects_a_misread_balance_row_and_flags_missing_filings():
    html = _html([["درآمدهای عملیاتی", "1,000", "800"], ["سود (زیان) خالص", "100", "80"], ["جمع دارایی‌ها", "2,000", "1,800"],
                  ["جمع بدهی‌ها", "1,200", "1,100"], ["جمع حقوق مالکانه", "800", "700"]])
    stored = _codal(0, total_assets_current=300.0, total_assets_prev=250.0, tracing_no="T1")
    res = verify_statement("X", stored, lambda t: html)
    assert res["status"] == "corrected" and res["values"]["total_assets_current"] == 2000.0
    assert abs(res["storedGap"]) > 0.02 and abs(res["filingGap"]) <= 0.02
    same = verify_statement("X", _codal(0, tracing_no="T1", revenue_current=1000.0, net_profit_current=100.0), lambda t: html)
    assert same["status"] in ("verified", "corrected")

    def miss(_t):
        raise RuntimeError("no report")
    res2 = verify_statement("X", stored, miss)
    assert res2["status"] == "unverified" and "not in the CODAL inbox" in res2["reason"]
    assert verify_statement("X", {**stored, "tracing_no": None}, miss)["status"] == "unverified"


# ---- statistics -----------------------------------------------------------------------------

def test_spearman_is_not_dominated_by_one_outlier():
    xs = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, -1000.0]
    ys = [9, 1, 7, 3, 8, 2, 6, 4, 5, 10, 0, 11, -1000.0]
    assert st.pearson(xs, ys) > 0.99          # the outlier fabricates a perfect correlation
    assert abs(st.spearman(xs, ys)) < 0.6     # ranks do not


# ---- EDA: company-specific vs market-wide ----------------------------------------------------

def test_eda_company_block_uses_the_company_own_numbers_and_labels_market_blocks():
    uni = _universe()
    ds = md.build_company_dataset(_item("S3", _codal(3), {"last_price": 1003, "pe": 8.0}), history=[{"observed_date": f"2026-10-{d:02d}", "price": 1000 + d} for d in range(1, 11)])
    e = mc.eda(ds, uni)
    prof = next(b for b in e["blocks"] if b.get("scopeKind") == "company" and "source" in b.get("columns", []))
    nm = next(r for r in prof["rows"] if r["column"] == "حاشیه سود خالص")
    assert math.isclose(nm["value"], round(103.0 / 1030.0, 4)) and nm["source"].startswith("CODAL")
    assert nm["sampleN"] == 12 and nm["percentile"] is not None
    market_blocks = [b for b in e["blocks"] if b.get("scopeKind") == "market"]
    assert market_blocks and all(("کل بازار" in b["title"] or "نمونه" in b["title"] or "همبستگی" in b["title"]) for b in market_blocks)
    line = next(b for b in e["blocks"] if b["type"] == "line")
    assert len(line["points"]) == 10 and "10 مشاهده" in line["title"]


def test_eda_without_company_data_is_blocked_not_filled_with_market_statistics():
    uni = _universe()
    ds = md.build_company_dataset({"code": "Z", "symbol": "Z", "name": "Z", "market": None, "enrichedAt": None, "company": None, "registryOnly": True})
    e = mc.eda(ds, uni)
    assert e["status"] == "blocked"
    assert not any(b["type"] in ("histogram",) for b in e["blocks"])


def test_eda_market_missing_company_states_exact_reason_and_keeps_history():
    uni = _universe()
    ds = md.build_company_dataset(_item("S4", _codal(4)), history=[{"observed_date": f"2026-10-{d:02d}", "price": 3000 + d} for d in range(1, 49 - 30)])
    e = mc.eda(ds, uni)
    prof = next(b for b in e["blocks"] if b.get("scopeKind") == "company" and "source" in b.get("columns", []))
    pe = next(r for r in prof["rows"] if r["column"] == "P/E")
    assert pe["value"] is None and "قیمت" in pe["reason"]
    assert next(b for b in e["blocks"] if b["type"] == "line")["points"]


def test_histogram_marks_when_company_is_outside_the_plotted_range():
    uni = _universe()
    ds = md.build_company_dataset(_item("S5", _codal(5, net_profit_current=900.0)))
    e = mc.eda(ds, uni, column="net_margin")
    h = next(b for b in e["blocks"] if b["type"] == "histogram")
    assert h["marker"] is not None and h["markerInRange"] is False and "خارج از بازه" in h["note"]


# ---- KPI ------------------------------------------------------------------------------------

def test_kpi_public_items_never_require_private_data_and_history_close_is_not_a_current_price():
    ds = md.build_company_dataset(_item("S6", _codal(6)), history=[{"observed_date": "2026-09-01", "price": 3650.0}], now_iso="2026-11-06T00:00:00+00:00")
    k = mc.kpi(ds)
    items = k["blocks"][0]["items"]
    assert all(i["kind"] == "public" and i["requiresPrivateData"] is False for i in items)
    cur = next(i for i in items if i["key"] == "price")
    last = next(i for i in items if i["key"] == "last_recorded_close")
    assert cur["status"] == "missing" and cur["missing"] and last["value"] == 3650.0 and "قیمت جاری نیست" in last["formula"]
    assert any("Excel" in (b.get("text") or "") and b.get("privateKpis") for b in k["blocks"])


def test_kpi_marks_balance_sheet_ratios_unverified_with_reason():
    ds = md.build_company_dataset(_item("S7", _codal(7, total_assets_current=10.0)))
    k = mc.kpi(ds)
    roa = next(i for i in k["blocks"][0]["items"] if i["key"] == "roa")
    assert roa["status"] == "unverified" and roa["value"] is None and roa["missing"]


def test_reparse_clears_rejected_optional_values_and_refreshes_derived_percentages():
    html = _html([["درآمدهای عملیاتی", "1,000", "800"], ["سود (زیان) خالص", "100", "80"], ["جمع دارایی‌ها", "2,000", "1,800"],
                  ["جمع بدهی‌ها", "1,200", "1,100"], ["جمع حقوق مالکانه", "800", "700"], ["جمع بدهی‌های جاری", "9,999", "9,000"]])
    stored = _codal(0, tracing_no="T2", current_liabilities_current=9999.0, current_liabilities_prev=9000.0,
                    revenue_current=500.0, net_margin_pct=99.0, revenue_yoy_pct=1.0)
    res = verify_statement("X", stored, lambda t: html)
    assert res["status"] == "corrected"
    assert res["values"]["current_liabilities_current"] is None          # larger than total liabilities: rejected, cleared
    assert "current_liabilities_current" in res["changed"]
    assert abs(res["values"]["net_margin_pct"] - 10.0) < 1e-9 and abs(res["values"]["revenue_yoy_pct"] - 25.0) < 1e-9


def test_side_by_side_balance_sheet_rows_use_only_their_own_numbers():
    """Assets (left) and equity+liabilities (right) share one table row; the parser must not fail closed on six numbers."""
    from codal_parser_v2 import row_values
    rows = [["جمع دارایی‌ها", "31,129,934", "25,424,549", "22", "جمع بدهی‌ها و حقوق صاحبان سهام", "31,129,934", "25,424,549", "22"],
            ["جمع بدهی‌ها", "5,908,746", "5,410,488", "9", "جمع حقوق صاحبان سهام", "25,221,188", "20,014,061", "26"]]
    assert row_values(rows, ("جمع دارایی‌ها",)) == (31129934.0, 25424549.0)
    assert row_values(rows, ("جمع بدهی‌ها",)) == (5908746.0, 5410488.0)
    assert row_values(rows, ("جمع حقوق صاحبان سهام",)) == (25221188.0, 20014061.0)
    assert row_values([["جمع دارایی‌ها", "1", "2", "3", "4", "5"]], ("جمع دارایی‌ها",)) is None   # five plain numbers stay fail-closed


def test_negative_equity_statement_still_balances():
    c = _codal(0, total_assets_current=13554.0, total_liabilities_current=227456.0, total_equity_current=-213902.0,
               total_assets_prev=10273.0, total_liabilities_prev=221028.0, total_equity_prev=-210755.0)
    assert md.build_company_dataset(_item("N", c))["fundamentals"]["verification"]["status"] == "verified"


def test_filing_header_reports_unit_and_period_and_a_period_mismatch_is_unverified():
    from codal_reparse import filing_header
    rows = [["جمع دارایی‌ها", "2,000", "1,800"], ["جمع بدهی‌ها", "1,200", "1,100"], ["جمع حقوق مالکانه", "800", "700"],
            ["درآمدهای عملیاتی", "1,000", "800"], ["سود (زیان) خالص", "100", "80"]]
    html = "<html><body><p>کلیه مبالغ درج شده به میلیون ریال می باشد</p><p>عملکرد واقعی منتهی به ۱۴۰۴/۱۲/۲۹</p>" + _html(rows)[len("<html><body>"):]
    assert filing_header(html) == {"unit": "میلیون ریال", "periodEnd": "1404/12/29"}
    ok = verify_statement("X", _codal(0, tracing_no="T3"), lambda t: html)
    assert ok["status"] in ("verified", "corrected") and ok["filing"]["unit"] == "میلیون ریال"
    bad = verify_statement("X", _codal(0, tracing_no="T3", report_title="صورت‌های مالی سال مالی منتهی به ۱۴۰۳/۱۲/۳۰"), lambda t: html)
    assert bad["status"] == "unverified" and "period mismatch" in bad["reason"]


def test_statement_from_long_ago_is_stale_not_current_and_stays_out_of_peer_statistics():
    import datetime
    old = md.build_company_dataset(_item("O", _codal(0, report_title="صورت‌های مالی سال مالی منتهی به ۱۳۹۶/۰۸/۳۰")))
    v = old["fundamentals"]["verification"]
    assert v["stale"] is True and any("جاری نیست" in r for r in v["reasons"])
    assert md.build_company_dataset(_item("F", _codal(0)))["fundamentals"]["verification"]["stale"] is False
    uni = _universe()
    uni.append(dict(md.universe_row(_item("OLD", _codal(0, net_profit_current=999999.0, report_title="صورت‌های مالی سال مالی منتهی به ۱۳۹۶/۰۸/۳۰"))), is_primary=1, category="operating_company"))
    rows, _ = mc._column_rows(old, uni, "net_margin", False)
    assert all(r["code"] != "OLD" for r in rows)
    assert md.months_old("1404/12/29", datetime.date(2026, 11, 5)) == 8


def test_zero_or_negative_assets_are_unverified_not_verified():
    for ta in (0.0, -5.0):
        ds = md.build_company_dataset(_item("Z", _codal(0, total_assets_current=ta, total_liabilities_current=1200.0, total_equity_current=800.0)))
        v = ds["fundamentals"]["verification"]
        assert v["status"] == "unverified" and any("صفر یا منفی" in r for r in v["reasons"])
        assert ds["ratios"]["roe"]["value"] is None and ds["ratios"]["debt_to_equity"]["value"] is None


def test_reparse_compares_sga_and_depreciation_too():
    html = _html([["درآمدهای عملیاتی", "1,000", "800"], ["سود (زیان) خالص", "100", "80"], ["جمع دارایی‌ها", "2,000", "1,800"],
                  ["جمع بدهی‌ها", "1,200", "1,100"], ["جمع حقوق مالکانه", "800", "700"],
                  ["هزینه‌های فروش، اداری و عمومی", "(50)", "(40)"]])
    stored = _codal(0, tracing_no="T4", sga_expense_current=-999.0, sga_expense_prev=-40.0)
    res = verify_statement("X", stored, lambda t: html)
    assert res["status"] == "corrected" and res["changed"]["sga_expense_current"]["filing"] == -50.0


def test_correlation_pairs_exclude_stale_and_unverified_statements():
    uni = _universe(8)
    for i in range(12):
        row = dict(md.universe_row(_item(f"OLD{i}", _codal(i, report_title="صورت‌های مالی سال مالی منتهی به ۱۳۹۶/۰۸/۳۰"))), is_primary=1, category="operating_company")
        uni.append(row)
    ds = md.build_company_dataset(_item("S1", _codal(1)))
    e = mc.eda(ds, uni)
    corr = next(b for b in e["blocks"] if "همبستگی" in (b.get("title") or ""))
    assert all(r["n"] <= 8 for r in corr["rows"]) and corr["rows"] == []   # 8 eligible < 15 required pairs


def test_market_entry_and_peer_pool_ignore_stale_and_unverified_statements():
    uni = _universe(8)
    for i in range(12):
        uni.append(dict(md.universe_row(_item(f"OLD{i}", _codal(i, net_profit_current=5000.0, report_title="صورت‌های مالی سال مالی منتهی به ۱۳۹۶/۰۸/۳۰"))),
                        is_primary=1, category="operating_company", sector="X"))
    for r in uni[:8]:
        r["sector"] = "X"
    ds = md.build_company_dataset(_item("S1", _codal(1), {"last_price": 1000, "sector_name": "X"}))
    assert all(r["code"].startswith("S") for r in mc.comparable(uni, "S1"))
    e = mc.market_entry(ds, uni)
    nm = [r for r in (e["blocks"][0].get("rows") or []) if r["metric"] == "حاشیه سود خالص"]
    assert nm and nm[0]["n"] == 8          # the 12 stale statements are not counted


def test_apply_bumps_updated_at_so_the_universe_cache_refreshes(tmp_path):
    import json as _json
    import sqlite3
    from codal_reparse import reparse
    from listed_company_store import ListedCompanyStore
    store = ListedCompanyStore(str(tmp_path / "l.sqlite3"))
    stored = _codal(0, total_assets_current=300.0, total_assets_prev=250.0, tracing_no="T9")
    store.save_enriched("AAA", {"ticker": "AAA", "name_fa": "AAA", "codal": stored}, provenance={})
    html = _html([["درآمدهای عملیاتی", "1,000", "800"], ["سود (زیان) خالص", "100", "80"], ["جمع دارایی‌ها", "2,000", "1,800"],
                  ["جمع بدهی‌ها", "1,200", "1,100"], ["جمع حقوق مالکانه", "800", "700"]])

    class Inbox:
        def report_html(self, t):
            return html
    conn = sqlite3.connect(store.db_path)
    before = conn.execute("SELECT updated_at FROM listed_companies WHERE code='AAA'").fetchone()[0]
    stamp0 = md.UniverseCache._db_stamp(store)
    res = reparse(store.db_path, apply=True, inbox=Inbox())
    assert res["counts"]["corrected"] == 1
    after = sqlite3.connect(store.db_path).execute("SELECT updated_at, company_json FROM listed_companies WHERE code='AAA'").fetchone()
    assert after[0] != before and md.UniverseCache._db_stamp(store) != stamp0
    assert _json.loads(after[1])["codal"]["total_assets_current"] == 2000.0


def _empty_quote_item():
    it = _item("Q", _codal(0))
    it["company"]["market"] = {k: None for k in ("last_price", "closing_price", "price", "pe", "market_cap", "change_percent")}
    return it


def test_recent_recorded_close_fills_an_empty_quote_and_is_labelled_with_its_date():
    hist = [{"observed_date": "2026-11-04", "price": 3650.0, "pe": 16.3, "market_cap": 8.869e14, "change_percent": 2.8, "source": "kiasha:tsetmc"},
            {"observed_date": "2026-11-05", "price": 3630.0, "pe": 16.4, "market_cap": 8.918e14, "change_percent": 2.25, "source": "kiasha:tsetmc"}]
    ds = md.build_company_dataset(_empty_quote_item(), hist, now_iso="2026-11-06T01:00:00+00:00")
    assert ds["market"]["price"] == 3630.0 and ds["market"]["pe"] == 16.4 and ds["market"]["market_cap"] == 8.918e14
    assert ds["provenance"]["priceSource"] == "history:2026-11-05" and ds["quality"]["priceFromHistory"] == "2026-11-05"
    assert ds["status"]["hasCurrentPrice"] is True and "MISSING_MARKET" not in ds["status"]["codes"]


def test_old_recorded_close_is_not_presented_as_current_and_a_real_quote_always_wins():
    old = [{"observed_date": "2026-10-01", "price": 3000.0, "pe": 10.0}]
    ds = md.build_company_dataset(_empty_quote_item(), old, now_iso="2026-11-06T01:00:00+00:00")
    assert ds["market"]["price"] is None and "MISSING_MARKET" in ds["status"]["codes"] and "priceFromHistory" not in ds["quality"]
    live = _item("L", _codal(0)); live["company"]["market"] = {"last_price": 4000.0, "pe": 12.0}
    ds2 = md.build_company_dataset(live, [{"observed_date": "2026-11-05", "price": 3630.0, "pe": 16.4}], now_iso="2026-11-06T01:00:00+00:00")
    assert ds2["market"]["price"] == 4000.0 and ds2["market"]["pe"] == 12.0 and "priceFromHistory" not in ds2["quality"]



def test_same_day_observation_uses_latest_recorded_timestamp_not_first_source():
    hist = [
        {"observed_date": "2026-11-05", "observed_at": "2026-11-05T13:02:00+00:00",
         "price": 3540, "pe": 13.0, "source": "first-source"},
        {"observed_date": "2026-11-05", "observed_at": "2026-11-05T17:25:00+00:00",
         "price": 3630, "pe": 16.4, "source": "newest-source"},
        {"observed_date": "2026-11-04", "observed_at": "2026-11-04T23:59:00+00:00",
         "price": 9999, "pe": 50.0, "source": "older-date"},
    ]
    ds = md.build_company_dataset(_empty_quote_item(), hist, now_iso="2026-11-06T01:00:00+00:00")
    assert ds["market"]["price"] == 3630 and ds["market"]["pe"] == 16.4
    assert ds["provenance"]["priceSource"] == "history:2026-11-05"

    # Input order is not a proxy for recency when explicit timestamps exist.
    reversed_ds = md.build_company_dataset(_empty_quote_item(), list(reversed(hist)),
                                           now_iso="2026-11-06T01:00:00+00:00")
    assert reversed_ds["market"]["price"] == 3630


def test_same_day_without_timestamps_uses_last_history_row():
    hist = [{"observed_date": "2026-11-05", "price": 3500},
            {"observed_date": "2026-11-05", "price": 3600}]
    ds = md.build_company_dataset(_empty_quote_item(), hist, now_iso="2026-11-06T01:00:00+00:00")
    assert ds["market"]["price"] == 3600


def test_swot_threat_shows_audit_opinion_in_persian_not_english():
    for op, fa in (("qualified", "مشروط"), ("adverse", "مردود"), ("disclaimer", "عدم اظهارنظر")):
        ds = md.build_company_dataset(_item("W" + op, _codal(0)))
        ds["fundamentals"]["auditOpinion"] = op
        threats = next(b for b in mc.swot(ds, _universe())["blocks"] if b["type"] == "swot")["threats"]
        text = " ".join(threats)
        assert f"نظر حسابرس: {fa}" in text and op not in text
    ds = md.build_company_dataset(_item("Wok", _codal(0))); ds["fundamentals"]["auditOpinion"] = "unqualified"
    assert "نظر حسابرس" not in " ".join(next(b for b in mc.swot(ds, _universe())["blocks"] if b["type"] == "swot")["threats"])


def test_swot_competitors_show_names_and_collapse_sub_symbols():
    uni = _universe()
    own = md.build_company_dataset(_item("OWN", _codal(0)))
    for code, sym, nm, cap in (("a", "فخوز", "فولاد خوزستان", 9.0), ("b", "فخوز2", "فولاد خوزستان", 8.0), ("c", "فخوز3", "فولاد خوزستان", 7.0),
                               ("d", "مبین", "مبین انرژی", 6.0), ("e", "مبین3", "مبین انرژی", 5.0)):
        uni.append({**uni[0], "code": code, "symbol": sym, "name": nm, "market_cap": cap, "is_primary": 1, "category": uni[0].get("category")})
    rows = next(b for b in mc.swot(own, uni)["blocks"] if b["type"] == "table")["rows"]
    names = [r["name"] for r in rows if r["name"] in ("فولاد خوزستان", "مبین انرژی")]
    assert names.count("فولاد خوزستان") == 1 and names.count("مبین انرژی") == 1
    assert set(rows[0]) == {"name", "symbol", "pe", "debt_ratio", "roe", "net_margin"}


# ---- audit opinion details ---------------------------------------------------------------------

_AUDIT_TEXT = ("گزارش حسابرس مستقل صورت‌های مالی تلفیقی اظهارنظر مشروط به نظر این مؤسسه به استثنای آثار مورد مندرج در بند مبنای اظهارنظر مشروط "
               "صورت‌های مالی وضعیت مالی گروه را به نحو منصفانه نشان می‌دهد مبنای اظهارنظر مشروط حسابرسی ما طبق استانداردهای حسابرسی انجام شده است "
               "در حساب‌های دریافتنی مبلغ ۱۲۰ میلیارد ریال وصول‌نشده است و ذخیره‌ای شناسایی نشده است مسئولیت هیئت مدیره در قبال صورت‌های مالی "
               "مؤسسه حسابرسی آزمون پرداز ایران مشهود تاریخ ۱۴۰۵/۰۲/۱۰ شریک مسئول")


def test_audit_basis_and_auditor_firm_are_extracted_verbatim_or_not_at_all():
    from audit_parser import extract_audit_basis, extract_auditor_name
    basis = extract_audit_basis(_AUDIT_TEXT)
    assert basis and basis.startswith("حسابرسی ما طبق استانداردهای") and "۱۲۰ میلیارد ریال" in basis and "مسئولیت هیئت مدیره" not in basis
    assert extract_auditor_name(_AUDIT_TEXT) == "مؤسسه حسابرسی آزمون پرداز ایران مشهود"
    assert extract_audit_basis("متن بدون بخش مبنا") is None and extract_auditor_name("متن بدون نام") is None


def test_unaudited_statement_never_carries_an_auditor_opinion():
    unaudited = _codal(0, report_title="صورت‌های مالی تلفیقی سال مالی منتهی به ۱۴۰۴/۱۲/۲۹ (حسابرسی نشده)", audit_opinion="qualified")
    f = md.build_company_dataset(_item("U1", unaudited))["fundamentals"]
    assert f["auditStatus"] == "unaudited" and f["auditOpinion"] is None
    audited = md.build_company_dataset(_item("U2", _codal(0, report_title="صورت‌های مالی سال مالی منتهی به ۱۴۰۴/۱۲/۲۹ (حسابرسی شده)", audit_opinion="qualified",
                                                     auditor_name="موسسه حسابرسی الف", audit_basis="متن مبنا")))["fundamentals"]
    assert audited["auditStatus"] == "audited" and audited["auditOpinion"] == "qualified" and audited["auditorName"] == "موسسه حسابرسی الف" and audited["auditBasis"] == "متن مبنا"
    assert md.is_unaudited_title("صورت‌های مالی (حسابرسي نشده)") is True


def test_listed_business_kpi_is_filled_from_codal_and_asks_only_for_customer_metrics():
    ds = md.build_company_dataset(_item("BK", _codal(0, gross_profit_current=400.0, gross_profit_prev=300.0)))
    out = mc.compute("business-kpi", ds, _universe())
    assert out["status"] == "partial" and out["missing"] == mc.CUSTOMER_METRICS
    table = next(b for b in out["blocks"] if b["type"] == "table")
    by = {r["metric"]: r for r in table["rows"]}
    cur = ds["fundamentals"]["current"]
    assert by["درآمد عملیاتی"]["value"] == cur["revenue"] and by["سود خالص"]["value"] == cur["net_profit"]
    assert by["بهای تمام‌شده درآمد"]["value"] == pytest.approx(cur["revenue"] - cur["gross_profit"])
    assert by["حاشیه سود خالص"]["value"] == pytest.approx(round(cur["net_profit"] / cur["revenue"], 4), abs=1e-3)
    assert not any("مشتری" in r["metric"] for r in table["rows"])  # never guessed
    no_gp = mc.compute("business-kpi", md.build_company_dataset(_item("BK2", _codal(0))), _universe())
    assert "بهای تمام‌شده درآمد" not in {r["metric"] for r in next(b for b in no_gp["blocks"] if b["type"] == "table")["rows"]}  # no gross profit -> no invented cost
    assert "مشتری فعال" in " ".join(b.get("text", "") for b in out["blocks"])


def test_listed_business_kpi_withheld_when_statement_unverified_or_missing():
    unver = md.build_company_dataset(_item("BU", _codal(0, total_assets_current=10.0)))
    out = mc.compute("business-kpi", unver, _universe())
    assert out["status"] == "blocked" and "ارقام آن نمایش داده نمی‌شود" in out["summary"]
    none = md.build_company_dataset({"code": "N", "symbol": "N", "name": "N", "market": "TSE", "company": {}})
    assert mc.compute("business-kpi", none, _universe())["status"] == "blocked"
