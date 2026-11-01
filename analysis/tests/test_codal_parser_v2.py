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

def test_balance_sheet_totals_are_not_noncurrent_subtotals():
    html = """
    <table>
      <tr><td>درآمدهای عملیاتی</td><td>1,000</td><td>800</td></tr>
      <tr><td>سود (زیان) خالص</td><td>100</td><td>80</td></tr>
      <tr><td>جمع دارایی های غیرجاری</td><td>160</td><td>120</td></tr>
      <tr><td>جمع دارایی های جاری</td><td>180</td><td>140</td></tr>
      <tr><td>جمع دارایی ها</td><td>340</td><td>260</td></tr>
      <tr><td>جمع حقوق مالکانه</td><td>40</td><td>30</td></tr>
      <tr><td>جمع بدهی های غیرجاری</td><td>130</td><td>100</td></tr>
      <tr><td>جمع بدهی های جاری</td><td>170</td><td>130</td></tr>
      <tr><td>جمع بدهی ها</td><td>300</td><td>230</td></tr>
      <tr><td>جمع حقوق مالکانه و بدهی ها</td><td>340</td><td>260</td></tr>
    </table>
    """
    result = parse_fundamentals("پکرمان", _filing(), html)
    assert result is not None
    assert (result.total_assets_current, result.total_liabilities_current,
            result.total_equity_current) == (340, 300, 40)
    assert result.total_assets_current == result.total_liabilities_current + result.total_equity_current


def test_balance_sheet_subtotals_alone_do_not_become_totals():
    html = """
    <table>
      <tr><td>درآمدهای عملیاتی</td><td>1,000</td><td>800</td></tr>
      <tr><td>سود (زیان) خالص</td><td>100</td><td>80</td></tr>
      <tr><td>جمع دارایی های غیرجاری</td><td>160</td><td>120</td></tr>
      <tr><td>جمع بدهی های غیرجاری</td><td>130</td><td>100</td></tr>
      <tr><td>جمع حقوق مالکانه و بدهی ها</td><td>340</td><td>260</td></tr>
    </table>
    """
    result = parse_fundamentals("پکرمان", _filing(), html)
    assert result is not None
    assert result.total_assets_current is None
    assert result.total_liabilities_current is None
    assert result.total_equity_current is None
