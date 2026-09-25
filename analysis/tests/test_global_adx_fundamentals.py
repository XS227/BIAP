from __future__ import annotations

from global_markets.adx_fundamentals import parse_adx_financial_summary


def test_adx_financial_summary_uses_latest_completed_annual_row():
    payload = {
        "response": {
            "data": [
                {"netProfit":"6503939463.0","shareCapital":"7862629617.0","totalEquity":"42795908962.0","earningsPerShare":"0.699","priceToBookValue":"1.462","financialYear":"2024","financialQuarter":"Annual"},
                {"netProfit":"8833580921.0","shareCapital":"7862629617.0","totalEquity":"48751989579.0","earningsPerShare":"0.955","priceToBookValue":"1.664","financialYear":"2025","financialQuarter":"Annual"},
                {"netProfit":"4859529401.0","shareCapital":"7862629210.0","totalEquity":"51799068805.0","earningsPerShare":"0.529","priceToBookValue":"1.161","financialYear":"2026","financialQuarter":"H1"},
            ]
        },
        "resultCode": "S",
        "resultMessage": "Success",
    }
    latest, rows = parse_adx_financial_summary(payload)
    assert len(rows) == 3
    assert latest["financialYear"] == "2025"
    assert latest["netProfit"] == "8833580921.0"
