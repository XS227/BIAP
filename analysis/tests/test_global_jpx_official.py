import io

import openpyxl

from global_markets.jpx_official import is_jpx_domestic_common, parse_jpx_workbook


def test_jpx_domestic_filter_excludes_products_foreign_and_class_shares():
    assert is_jpx_domestic_common("1301", "Prime Market (Domestic)")
    assert is_jpx_domestic_common("130A", "Growth Market(Domestic)")
    assert is_jpx_domestic_common(1332, "Prime Market (Domestic)")
    assert not is_jpx_domestic_common("1305", "ETFs/ ETNs")
    assert not is_jpx_domestic_common("25935", "Prime Market (Domestic)")
    assert not is_jpx_domestic_common("50765", "Prime Market (Domestic)")
    assert not is_jpx_domestic_common("9999", "Standard Market(Foreign)")
    assert not is_jpx_domestic_common("131A", "PRO Market")


def test_parse_jpx_workbook_keeps_only_domestic_ordinary_equities():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "Effective Date", "Local Code", "Name (English)", "Section/Products",
        "33 Sector(Code)", "33 Sector(name)", "17 Sector(Code)", "17 Sector(name)",
        "Size Code (New Index Series)", "Size (New Index Series)",
    ])
    ws.append(["20260831", 1301, "KYOKUYO", "Prime Market (Domestic)", "50", "Fishery", "1", "FOODS", "6", "Small"])
    ws.append(["20260831", "130A", "Veritas", "Growth Market(Domestic)", "3250", "Pharmaceutical", "5", "PHARMA", "-", "-"])
    ws.append(["20260831", 1305, "ETF", "ETFs/ ETNs", "-", "-", "-", "-", "-", "-"])
    ws.append(["20260831", 25935, "Preferred", "Prime Market (Domestic)", "3050", "Foods", "1", "FOODS", "-", "-"])
    out = io.BytesIO()
    wb.save(out)
    effective, rows = parse_jpx_workbook(out.getvalue())
    assert effective == "20260831"
    assert [row["code"] for row in rows] == ["1301", "130A"]
