from __future__ import annotations

from global_markets.adx_fundamentals import (
    parse_adx_disclosure_metrics,
    parse_adx_financial_summary,
    select_latest_adx_annual_report,
)


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



def test_adx_selects_latest_annual_financial_report_and_parses_metrics():
    annual_2025 = {
        "entity": "ALDAR",
        "subCategoryNameEn": "Financial Reports | Financial Report",
        "simpleTitleEn": "Financial Results for the Period Ended December 31,2025",
        "publishedDate": "2026-02-09 00:00:00.0",
        "urlEn": "https://apigateway.adx.ae/adx/cdn/1.0/content/download/4692155",
        "aiJsonDataEn": '{"table":{"columns":[{"key":"col1","label":"Metric"},{"key":"col2","label":"2025"},{"key":"col3","label":"2024"},{"key":"col4","label":"YoY Change"}],"rows":[{"col1":"Revenue","col2":"33.818B","col3":"22.998B","col4":"+47.0%"},{"col1":"Net Profit","col2":"8.834B","col3":"6.504B","col4":"+35.8%"},{"col1":"EPS","col2":"0.955","col3":"0.699","col4":"+36.6%"},{"col1":"Cash and Cash Equivalents","col2":"14.161B","col3":"10.223B","col4":"+38.5%"}]}}',
    }
    payload = {
        "response": {
            "news": [
                {
                    "entity": "ALDAR",
                    "subCategoryNameEn": "Financial Reports | Financial Report",
                    "simpleTitleEn": "Financial Results for the Period Ended June 30,2026",
                    "publishedDate": "2026-07-29 00:00:00.0",
                    "urlEn": "https://example.invalid/h1.pdf",
                    "aiJsonDataEn": "{}",
                },
                annual_2025,
                {
                    "entity": "ALDAR",
                    "subCategoryNameEn": "Financial Reports | Financial Press Release",
                    "simpleTitleEn": "Financial Results Press Release for the Period Ended December 31,2025",
                    "publishedDate": "2026-02-09 00:00:00.0",
                    "urlEn": "https://example.invalid/pr.pdf",
                    "aiJsonDataEn": "{}",
                },
            ]
        }
    }
    selected = select_latest_adx_annual_report(payload, "ALDAR")
    assert selected["urlEn"].endswith("4692155")
    metrics = parse_adx_disclosure_metrics(selected)
    assert metrics["revenue"] == 33_818_000_000.0
    assert metrics["revenue_prev"] == 22_998_000_000.0
    assert metrics["revenue_yoy_pct"] == 47.0
    assert metrics["net_income"] == 8_834_000_000.0
    assert metrics["eps"] == 0.955
    assert metrics["cash_and_equivalents"] == 14_161_000_000.0
