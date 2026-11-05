"""Regression + independent numeric validation for the Iran module repair (digits, verification, EDA scope, KPI, re-parse)."""
import math

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
    ds = md.build_company_dataset(_item("S6", _codal(6)), history=[{"observed_date": "2026-11-04", "price": 3650.0}])
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
