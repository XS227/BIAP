from codal_data import CodalFiling
from codal_parser_v2 import parse_fundamentals


def _filing():
    return CodalFiling("1", "صورت های مالی", None, None, None, None, None, "https://excel.codal.ir/x", None)


def test_parser_accepts_note_suffix_and_common_revenue_label():
    html = """
    <table>
      <tr><td>فروش خالص - یادداشت 12</td><td>1,200</td><td>1,000</td></tr>
      <tr><td>سود (زیان) خالص دوره</td><td>240</td><td>150</td></tr>
    </table>
    """
    result = parse_fundamentals("نماد", _filing(), html)
    assert result is not None
    assert result.revenue_current == 1200
    assert result.revenue_prev == 1000
    assert result.revenue_yoy_pct == 20
    assert result.net_margin_pct == 20


def test_parser_extracts_cash_flow_and_current_items_without_guessing():
    html = """
    <table>
      <tr><td>درآمدهای عملیاتی</td><td>1,200</td><td>1,000</td></tr>
      <tr><td>سود (زیان) خالص</td><td>240</td><td>150</td></tr>
      <tr><td>جمع دارایی‌های جاری</td><td>600</td><td>500</td></tr>
      <tr><td>جمع دارایی‌ها</td><td>1,000</td><td>900</td></tr>
      <tr><td>جمع بدهی‌های جاری</td><td>300</td><td>250</td></tr>
      <tr><td>جمع بدهی‌ها</td><td>400</td><td>350</td></tr>
      <tr><td>جمع حقوق مالکانه</td><td>600</td><td>550</td></tr>
      <tr><td>دریافتنی‌های تجاری و سایر دریافتنی‌ها</td><td>200</td><td>180</td></tr>
      <tr><td>سود انباشته</td><td>(50)</td><td>40</td></tr>
      <tr><td>جريان ‌خالص ‌ورود‌ (خروج) ‌نقد حاصل از فعاليت‌هاي ‌عملياتي</td><td>180</td><td>(30)</td><td>700</td></tr>
    </table>
    """
    r = parse_fundamentals("نماد", _filing(), html)
    assert r is not None
    assert (r.operating_cash_flow_current, r.operating_cash_flow_prev) == (180, -30)
    assert (r.current_assets_current, r.current_liabilities_current) == (600, 300)
    assert r.receivables_current == 200
    assert (r.retained_earnings_current, r.retained_earnings_prev) == (-50, 40)
    assert r.fixed_assets_current is None


def test_parser_drops_current_items_that_contradict_the_balance_sheet():
    html = """
    <table>
      <tr><td>درآمدهای عملیاتی</td><td>1,200</td><td>1,000</td></tr>
      <tr><td>سود (زیان) خالص</td><td>240</td><td>150</td></tr>
      <tr><td>جمع دارایی‌های جاری</td><td>1,500</td><td>500</td></tr>
      <tr><td>جمع دارایی‌ها</td><td>1,000</td><td>900</td></tr>
      <tr><td>جمع بدهی‌ها</td><td>400</td><td>350</td></tr>
      <tr><td>جمع حقوق مالکانه</td><td>600</td><td>550</td></tr>
    </table>
    """
    r = parse_fundamentals("نماد", _filing(), html)
    assert r is not None and r.current_assets_current is None


def test_parser_extracts_operating_profit_sga_and_checks_depreciation_columns():
    html = """
    <table>
      <tr><td>درآمدهای عملیاتی</td><td>1,200</td><td>1,000</td></tr>
      <tr><td>هزینه‏ هاى فروش، ادارى و عمومى</td><td>(150)</td><td>(120)</td><td>(25)</td></tr>
      <tr><td>سود(زیان) عملیاتى</td><td>300</td><td>200</td><td>50</td></tr>
      <tr><td>سود (زیان) خالص</td><td>240</td><td>150</td></tr>
      <tr><td>هزینه استهلاک</td><td>2,123</td><td>2,205</td><td>3,935</td></tr>
    </table>
    """
    r = parse_fundamentals("نماد", _filing(), html)
    assert r is not None
    assert (r.operating_profit_current, r.operating_profit_prev) == (300, 200)
    assert (r.sga_expense_current, r.sga_expense_prev) == (-150, -120)
    assert r.depreciation_current is None  # third column is not the % change: rejected, not guessed


def test_parser_accepts_depreciation_when_percent_column_is_consistent():
    html = """
    <table>
      <tr><td>درآمدهای عملیاتی</td><td>1,200</td><td>1,000</td></tr>
      <tr><td>سود (زیان) خالص</td><td>240</td><td>150</td></tr>
      <tr><td>هزینه استهلاک</td><td>110</td><td>100</td><td>10</td></tr>
    </table>
    """
    r = parse_fundamentals("نماد", _filing(), html)
    assert (r.depreciation_current, r.depreciation_prev) == (110, 100)
