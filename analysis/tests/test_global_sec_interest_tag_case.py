from global_markets.models import GlobalCompany
from global_markets.sec_edgar import SECEdgarFundamentalsProvider
from tests.test_global_sec_dividend import _concept


def _enrich(tags):
    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test test@example.com")
    provider._resolve_cik = lambda company: 1318605
    provider._get_json = lambda url: {"entityName": "Tesla, Inc.", "facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(94_800_000_000, end="2025-12-31", filed="2026-01-29"),
        "NetIncomeLoss": _concept(7_100_000_000, end="2025-12-31", filed="2026-01-29"),
        "Assets": _concept(137_000_000_000, end="2025-12-31", filed="2026-01-29"),
        **tags}}}
    return provider.enrich_fundamentals(GlobalCompany(
        country="US", exchange="NASDAQ", mic_code="XNAS", currency="USD", ticker="TSLA", name="Tesla, Inc."))


def test_tesla_style_lowercase_nonoperating_interest_tag_is_read():
    c = _enrich({"InterestExpenseNonoperating": _concept(338_000_000, end="2025-12-31", filed="2026-01-29")})
    assert c.interest_expense == 338_000_000


def test_stale_interest_tag_does_not_beat_current_one():
    c = _enrich({
        "InterestExpense": _concept(156_000_000, end="2023-12-31", filed="2024-01-30"),
        "InterestExpenseNonoperating": _concept(338_000_000, end="2025-12-31", filed="2026-01-29"),
    })
    assert c.interest_expense == 338_000_000
