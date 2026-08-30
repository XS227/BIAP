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
