"""Robust parser for CODAL financial-statement HTML tables.

Keeps BIAP's conservative rule: only explicit statement rows are accepted. The
matcher tolerates footnotes, punctuation and common wording extensions without
inventing values or crossing report scopes.
"""
from __future__ import annotations

import re

from codal_data import CodalFiling, CodalFundamentals, _TableRows, _normalize_text, _parse_number


def _canonical_label(value: str) -> str:
    text = _normalize_text(value)
    text = text.replace("‌", " ").replace("ـ", " ")
    text = re.sub(r"[\[\]{}():؛;،,.\-_/\\]+", " ", text)
    text = re.sub(r"\b(?:یادداشت|شماره|توضیحات)\s*[۰-۹0-9]*\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace(" ", "")


def _matches(cell: str, aliases: tuple[str, ...]) -> bool:
    label = _canonical_label(cell)
    if not label:
        return False
    for alias in aliases:
        wanted = _canonical_label(alias)
        if label == wanted:
            return True
        # CODAL templates often append qualifiers such as «ادامه عملیات» or a
        # note number. Require the canonical accounting label to be the leading
        # phrase so unrelated rows are not matched accidentally.
        if len(wanted) >= 6 and label.startswith(wanted):
            suffix = label[len(wanted):]
            if len(suffix) <= 18:
                return True
    return False


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
        # Some exports repeat a note/index number immediately after the label.
        # Prefer the two largest-magnitude adjacent accounting values when more
        # than two numeric cells are present, but preserve original order.
        if len(numbers) >= 2:
            if len(numbers) == 2:
                return numbers[0], numbers[1]
            pairs = [(i, abs(numbers[i]) + abs(numbers[i + 1])) for i in range(len(numbers) - 1)]
            best = max(pairs, key=lambda item: item[1])[0]
            return numbers[best], numbers[best + 1]
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
    if revenue is None or net_profit is None:
        return None
    revenue_current, revenue_prev = revenue
    net_profit_current, net_profit_prev = net_profit
    if revenue_current == 0 or revenue_prev == 0:
        return None
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
    )
