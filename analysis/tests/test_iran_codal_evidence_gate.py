"""Iran-only CODAL identity gate: exact reasons, no made-up BUY decisions."""
from codal_data import CodalFiling
from codal_parser_v2 import parse_fundamentals, row_values
from codal_quality import review_iran_codal
import kiasha
from agents import AgentVote


def company(codal=None, is_available=True):
    if codal is None:
        codal = {
            "report_title": "صورت‌های مالی ۱۴۰۴/۱۲/۲۹",
            "report_url": "https://excel.codal.ir/test",
            "tracing_no": "123",
            "revenue_current": 1200,
            "revenue_prev": 1000,
            "net_profit_current": 100,
            "total_assets_current": 500,
            "total_liabilities_current": 300,
            "total_equity_current": 200,
            "total_assets_prev": 400,
            "total_liabilities_prev": 250,
            "total_equity_prev": 150,
        }
    return {"ticker": "TEST", "codal": codal, "data_available": {"codal": is_available}, "market": {}}


def test_quality_gate_passes_tying_statements_with_provenance():
    review = review_iran_codal(company())
    assert review["status"] == "PASS"
    assert review["actionable"] is True


def test_quality_gate_blocks_mixed_balance_sheet():
    sample = company()
    sample["codal"]["total_equity_current"] = 300
    review = review_iran_codal(sample)
    assert review["status"] == "BLOCK"
    assert "identity mismatch" in review["reasons"][0]


def test_quality_gate_warns_missing_balance_line():
    sample = company()
    sample["codal"]["total_assets_current"] = None
    assert review_iran_codal(sample)["status"] == "WARN"


def test_quality_gate_blocks_no_codal_even_when_technical_is_positive():
    sample = company(codal={}, is_available=False)
    assert review_iran_codal(sample)["actionable"] is False


def test_parser_refuses_ambiguous_three_column_row():
    assert row_values([["سود خالص", "2024", "125", "100"]], ("سود خالص",)) is None
    assert row_values([["سود خالص", "12", "125", "100"]], ("سود خالص",)) is None


def test_parser_uses_exact_total_rows_and_current_prior_columns():
    filing = CodalFiling("1531915", "صورت‌های مالی ۱۴۰۴/۱۲/۲۹", None, None, None, None, None, "https://excel.codal.ir/test", None)
    html = """
    <table>
    <tr><td>درآمدهای عملیاتی</td><td>12,085,377</td><td>8,792,140</td><td>37</td></tr>
    <tr><td>سود (زیان) خالص</td><td>8,166,298</td><td>8,109,459</td><td>1</td></tr>
    <tr><td>جمع دارایی‌های غیرجاری</td><td>78,503</td><td>843,393</td><td>843,540</td><td>(91)</td></tr>
    <tr><td>جمع دارایی‌های جاری</td><td>27,884,454</td><td>11,187,086</td><td>7,029,584</td><td>149</td></tr>
    <tr><td>جمع دارایی‌ها</td><td>27,962,957</td><td>12,030,479</td><td>7,873,124</td><td>132</td></tr>
    <tr><td>جمع حقوق مالکانه</td><td>24,826,686</td><td>10,660,238</td><td>7,590,779</td><td>133</td></tr>
    <tr><td>جمع بدهی‌های غیرجاری</td><td>141,311</td><td>82,517</td><td>54,603</td><td>71</td></tr>
    <tr><td>جمع بدهی‌های جاری</td><td>2,994,960</td><td>1,287,724</td><td>227,742</td><td>133</td></tr>
    <tr><td>جمع بدهی‌ها</td><td>3,136,271</td><td>1,370,241</td><td>282,345</td><td>129</td></tr>
    </table>
    """
    parsed = parse_fundamentals("سپیدار", filing, html)
    assert parsed is not None
    assert parsed.total_assets_current == 27_962_957
    assert parsed.total_liabilities_current == 3_136_271
    assert parsed.total_equity_current == 24_826_686
    assert parsed.total_assets_prev == 12_030_479
    assert parsed.total_liabilities_prev == 1_370_241
    assert parsed.total_equity_prev == 10_660_238
    assert parsed.revenue_current == 12_085_377


def test_parser_rejects_cross_table_non_tying_balance():
    filing = CodalFiling("123", "صورت‌های مالی", None, None, None, None, None, "https://excel.codal.ir/test", None)
    html = """
    <table>
    <tr><td>درآمدهای عملیاتی</td><td>1200</td><td>1000</td></tr>
    <tr><td>سود خالص</td><td>100</td><td>90</td></tr>
    </table>
    <table>
    <tr><td>جمع دارایی‌ها</td><td>500</td><td>400</td></tr>
    <tr><td>جمع بدهی‌ها</td><td>300</td><td>250</td></tr>
    <tr><td>جمع حقوق مالکانه</td><td>300</td><td>150</td></tr>
    </table>
    """
    assert parse_fundamentals("نماد", filing, html) is None


def test_kiasha_hold_blocks_positive_score_without_verified_fundamentals(monkeypatch):
    votes = [AgentVote(a, 0.9, 0.9, "positive") for a in ("fundamental", "risk", "forecast", "comparison", "technical", "flow")]
    monkeypatch.setattr(kiasha, "run_team", lambda _c: votes)
    monkeypatch.setattr(kiasha, "_scenario_signal", lambda _c: (None, None, 0.0))
    monkeypatch.setattr(kiasha, "_record_observation", lambda _c, _d: None)
    monkeypatch.setattr(kiasha, "_track_record_for_agent", lambda a: (kiasha.TRACK_RECORDS[a], "untrained-prior", 0))
    bad = company(codal={}, is_available=False)
    decision = kiasha.decide(bad)
    assert decision.weighted_score > 0.25
    assert decision.call == "HOLD"
    assert decision.evidence_review["status"] == "BLOCK"
    good = kiasha.decide(company())
    assert good.call == "BUY"
    assert good.evidence_review["status"] == "PASS"
