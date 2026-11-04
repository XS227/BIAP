"""Robust parser for CODAL financial-statement HTML tables.

Keeps BIAP's conservative rule: only explicit statement rows are accepted. The
matcher tolerates footnotes, punctuation and common wording extensions without
inventing values or crossing report scopes.
"""
from __future__ import annotations

import re

from codal_data import CodalFiling, CodalFundamentals, _TableRows, _normalize_text, _parse_number
from codal_quality import balance_sheet_check


def _canonical_label(value: str) -> str:
    text = _normalize_text(value)
    text = text.replace("‌", " ").replace("ـ", " ")
    text = re.sub(r"[\[\]{}():؛;،,.\-_/\\]+", " ", text)
    text = re.sub(r"\b(?:یادداشت|شماره|توضیحات)\s*[۰-۹0-9]*\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace(" ", "")


def _matches(cell: str, aliases: tuple[str, ...]) -> bool:
    # Match complete accounting labels only. Prefix matching accidentally
    # returned "current assets" / "noncurrent liabilities" instead of the
    # total rows in actual CODAL spreadsheets (e.g. سپیدار 1404).
    label = _canonical_label(cell)
    return bool(label) and any(label == _canonical_label(alias) for alias in aliases)


def row_values(rows: list[list[str]], aliases: tuple[str, ...]) -> tuple[float, float] | None:
    for row in rows:
        if not row:
            continue
        normalized = [_normalize_text(cell) for cell in row]
        label_idx = next((idx for idx, cell in enumerate(normalized) if _matches(cell, aliases)), None)
        if label_idx is None:
            continue
        values = [_parse_number(cell) for cell in row[label_idx + 1:]]
        numbers = [value for value in values if value is not None]
        if len(numbers) == 2:
            return numbers[0], numbers[1]
        if len(numbers) == 3 or len(numbers) == 4:
            # The real CODAL export uses current, prior, older/prior-to-prior,
            # and percent-change columns. Never choose the largest adjacent
            # values; those may belong to a different period.
            if numbers[0].is_integer() and 0 <= numbers[0] <= 99:
                if abs(numbers[1]) >= 100 and abs(numbers[2]) >= 100:
                    continue  # note index vs small current value: ambiguous
            if 1300 <= numbers[0] <= 2100 and all(abs(x) < 2000 for x in numbers[1:3]):
                continue  # year-looking numeric cell; ambiguous layout
            return numbers[0], numbers[1]
        # More than four numeric columns: unknown template, fail closed.
    return None


def parse_fundamentals(symbol: str, filing: CodalFiling, report_html: str) -> CodalFundamentals | None:
    parser = _TableRows()
    parser.feed(report_html)
    rows = parser.rows
    revenue = row_values(rows, (
        "درآمدهای عملیاتی", "درآمد عملیاتی", "جمع درآمدهای عملیاتی",
        "درآمد فروش", "فروش خالص", "جمع درآمد عملیاتی",
    ))
    net_profit = row_values(rows, (
        "سود (زیان) خالص", "سود خالص", "زیان خالص", "سود زیان خالص",
        "سود (زیان) خالص دوره", "سود خالص دوره",
    ))
    gross_profit = row_values(rows, (
        "سود (زیان) ناخالص", "سود ناخالص", "زیان ناخالص", "سود زیان ناخالص",
    ))
    total_assets = row_values(rows, (
        "جمع دارایی‌ها", "جمع دارایی ها", "جمع کل دارایی‌ها", "جمع داراییها", "جمع دارایی",
    ))
    total_liabilities = row_values(rows, (
        "جمع بدهی‌ها", "جمع بدهی ها", "جمع کل بدهی‌ها", "جمع بدهیها", "جمع بدهی",
    ))
    total_equity = row_values(rows, (
        "جمع حقوق مالکانه", "جمع حقوق صاحبان سهام", "جمع حقوق صاحبان سرمایه",
        "جمع حقوق صاحبان سهام شرکت اصلی", "جمع حقوق مالکانه شرکت اصلی",
    ))
    # Additive inputs for the audit checks. Exact-label match only; a value that contradicts the
    # balance sheet (e.g. current assets above total assets) is dropped rather than guessed.
    cfo = row_values(rows, (
        "جریان خالص ورود (خروج) نقد حاصل از فعالیت‌های عملیاتی",
        "جریان خالص ورود نقد حاصل از فعالیت‌های عملیاتی",
        "جریان خالص خروج نقد حاصل از فعالیت‌های عملیاتی",
        "جریان خالص ورود (خروج) وجه نقد حاصل از فعالیت‌های عملیاتی",
        "جریان خالص نقد حاصل از فعالیت‌های عملیاتی",
        "خالص جریان نقدی حاصل از فعالیت‌های عملیاتی",
    ))
    current_assets = row_values(rows, ("جمع دارایی‌های جاری", "جمع دارایی های جاری", "جمع داراییهای جاری"))
    current_liabilities = row_values(rows, ("جمع بدهی‌های جاری", "جمع بدهی های جاری", "جمع بدهیهای جاری"))
    receivables = row_values(rows, (
        "دریافتنی‌های تجاری و سایر دریافتنی‌ها", "دریافتنی‌های تجاری", "حساب‌ها و اسناد دریافتنی تجاری",
        "حساب‌های دریافتنی تجاری",
    ))
    retained = row_values(rows, ("سود (زیان) انباشته", "سود انباشته", "سود و زیان انباشته", "زیان انباشته"))
    fixed_assets = row_values(rows, ("دارایی‌های ثابت مشهود", "دارایی ثابت مشهود"))
    if revenue is None or net_profit is None:
        return None
    revenue_current, revenue_prev = revenue
    net_profit_current, net_profit_prev = net_profit
    if revenue_current == 0 or revenue_prev == 0:
        return None
    # Reject mixed balance-sheet rows before persisting them as CODAL evidence.
    balance = {
        "total_assets_current": total_assets[0] if total_assets else None,
        "total_assets_prev": total_assets[1] if total_assets else None,
        "total_liabilities_current": total_liabilities[0] if total_liabilities else None,
        "total_liabilities_prev": total_liabilities[1] if total_liabilities else None,
        "total_equity_current": total_equity[0] if total_equity else None,
        "total_equity_prev": total_equity[1] if total_equity else None,
    }
    for period in ("current", "prev"):
        status, _reason = balance_sheet_check(balance, period)
        if status == "BLOCK":
            return None
    def _pair(pair, index):
        return pair[index] if pair else None

    ta_cur, tl_cur = balance["total_assets_current"], balance["total_liabilities_current"]
    ta_prev, tl_prev = balance["total_assets_prev"], balance["total_liabilities_prev"]
    ca, cl, rec = current_assets, current_liabilities, receivables
    if ca and ta_cur is not None and ta_prev is not None and (ca[0] > ta_cur or ca[1] > ta_prev):
        ca = None
    if cl and tl_cur is not None and tl_prev is not None and (cl[0] > tl_cur or cl[1] > tl_prev):
        cl = None
    if rec and ca and (rec[0] > ca[0] or rec[1] > ca[1]):
        rec = None
    return CodalFundamentals(
        symbol=symbol,
        revenue_current=revenue_current,
        revenue_prev=revenue_prev,
        net_profit_current=net_profit_current,
        net_profit_prev=net_profit_prev,
        revenue_yoy_pct=(revenue_current - revenue_prev) / abs(revenue_prev) * 100.0,
        net_margin_pct=net_profit_current / revenue_current * 100.0,
        net_margin_prev_pct=net_profit_prev / revenue_prev * 100.0,
        gross_profit_current=gross_profit[0] if gross_profit else None,
        gross_profit_prev=gross_profit[1] if gross_profit else None,
        total_assets_current=total_assets[0] if total_assets else None,
        total_assets_prev=total_assets[1] if total_assets else None,
        total_liabilities_current=total_liabilities[0] if total_liabilities else None,
        total_liabilities_prev=total_liabilities[1] if total_liabilities else None,
        total_equity_current=total_equity[0] if total_equity else None,
        total_equity_prev=total_equity[1] if total_equity else None,
        tracing_no=filing.tracing_no,
        report_title=filing.title,
        report_url=filing.excel_url,
        source="codal_financial_statement_html_v2",
        operating_cash_flow_current=_pair(cfo, 0), operating_cash_flow_prev=_pair(cfo, 1),
        current_assets_current=_pair(ca, 0), current_assets_prev=_pair(ca, 1),
        current_liabilities_current=_pair(cl, 0), current_liabilities_prev=_pair(cl, 1),
        receivables_current=_pair(rec, 0), receivables_prev=_pair(rec, 1),
        retained_earnings_current=_pair(retained, 0), retained_earnings_prev=_pair(retained, 1),
        fixed_assets_current=_pair(fixed_assets, 0), fixed_assets_prev=_pair(fixed_assets, 1),
    )
