import pytest

from global_markets import service as service_module
from global_markets.models import GlobalCompany
from global_markets.source_cache import write_json_atomic
from global_markets.sec_edgar import SECEdgarFundamentalsProvider, sector_from_sic
from global_markets.service import _derive_metrics
from tests.test_global_sec_dividend import _concept


def _scan(tmp_path, monkeypatch, peers):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    write_json_atomic(tmp_path / "scan-cache" / "US" / "NASDAQ.json", {
        "schemaVersion": 3, "cachedAt": "2026-09-22T00:00:00+00:00",
        "payload": {"deepResults": [{"ticker": t, "company": {"ticker": t, "sector": s, "pe": pe}} for t, s, pe in peers]},
    })

    class _Now:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime
            return datetime(2026, 9, 22, 1, tzinfo=tz)

        @classmethod
        def fromisoformat(cls, value):
            from datetime import datetime
            return datetime.fromisoformat(value)
    monkeypatch.setattr(service_module, "datetime", _Now)


def _co(sector):
    return GlobalCompany(country="US", exchange="NASDAQ", mic_code="XNAS", currency="USD", ticker="TSLA",
                         name="Tesla", sector=sector, price=200.0, reporting_currency="USD", eps=4.0)


def test_exchange_wide_median_is_never_used_as_sector_pe(tmp_path, monkeypatch):
    peers = [(f"P{i}", "Technology", 20.0 + i) for i in range(6)]
    _scan(tmp_path, monkeypatch, peers)
    out = _derive_metrics(_co(None))
    assert out.sector_pe is None
    assert out.raw_provider_fields["peer_pe_benchmark_is_sector_specific"] is False
    assert out.raw_provider_fields["exchange_pe_median_informational"] == 22.5


def test_sector_without_enough_peers_does_not_fall_back_to_exchange(tmp_path, monkeypatch):
    peers = [(f"P{i}", "Technology", 20.0 + i) for i in range(6)]
    _scan(tmp_path, monkeypatch, peers)
    assert _derive_metrics(_co("Consumer Discretionary")).sector_pe is None


def test_three_same_sector_peers_give_sector_pe(tmp_path, monkeypatch):
    peers = [(f"A{i}", "Consumer Discretionary", pe) for i, pe in enumerate((10.0, 12.0, 14.0))] + [("T", "Technology", 90.0)]
    _scan(tmp_path, monkeypatch, peers)
    out = _derive_metrics(_co("Consumer Discretionary"))
    assert out.sector_pe == 12.0
    assert out.raw_provider_fields["peer_pe_benchmark_is_sector_specific"] is True


@pytest.mark.parametrize("sic,expected", [(3711, "Consumer Discretionary"), (7372, "Technology"), (2834, "Health Care"), (6021, "Financials"), (None, None), ("x", None)])
def test_sic_to_sector(sic, expected):
    assert sector_from_sic(sic) == expected


def _enrich(tags, sic=3711):
    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test test@example.com")
    provider._resolve_cik = lambda company: 1318605

    def get(url):
        if "submissions" in url:
            return {"sic": str(sic), "sicDescription": "Motor Vehicles & Passenger Car Bodies"}
        return {"entityName": "Tesla, Inc.", "facts": {"us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(94_800_000_000, end="2025-12-31", filed="2026-01-29"),
            "NetIncomeLoss": _concept(7_100_000_000, end="2025-12-31", filed="2026-01-29"),
            "Assets": _concept(137_000_000_000, end="2025-12-31", filed="2026-01-29"),
            **tags}}}
    provider._get_json = get
    return provider.enrich_fundamentals(GlobalCompany(
        country="US", exchange="NASDAQ", mic_code="XNAS", currency="USD", ticker="TSLA", name="Tesla, Inc."))


def test_tesla_ebitda_is_operating_income_plus_depreciation_and_marked_lower_bound():
    c = _enrich({
        "OperatingIncomeLoss": _concept(4_355_000_000, end="2025-12-31", filed="2026-01-29"),
        "Depreciation": _concept(5_030_000_000, end="2025-12-31", filed="2026-01-29"),
    })
    assert c.ebitda == 9_385_000_000
    d = c.raw_provider_fields["ebitda_derivation"]
    assert d["lower_bound"] is True and d["formula"] == "OperatingIncomeLoss + Depreciation"
    assert c.sector == "Consumer Discretionary" and c.raw_provider_fields["sector_source"] == "sec-sic"


def test_complete_da_tag_preferred_and_not_lower_bound():
    c = _enrich({
        "OperatingIncomeLoss": _concept(1_000, end="2025-12-31", filed="2026-01-29"),
        "Depreciation": _concept(300, end="2025-12-31", filed="2026-01-29"),
        "DepreciationDepletionAndAmortization": _concept(500, end="2025-12-31", filed="2026-01-29"),
    })
    assert c.ebitda == 1_500 and c.raw_provider_fields["ebitda_derivation"]["lower_bound"] is False


def test_no_ebitda_without_current_period_da_or_operating_income():
    assert _enrich({"OperatingIncomeLoss": _concept(1_000, end="2025-12-31", filed="2026-01-29")}).ebitda is None
    stale = _enrich({
        "OperatingIncomeLoss": _concept(1_000, end="2025-12-31", filed="2026-01-29"),
        "Depreciation": _concept(300, end="2023-12-31", filed="2024-01-29"),
    })
    assert stale.ebitda is None


def test_stale_complete_da_tag_does_not_shadow_current_depreciation():
    c = _enrich({
        "OperatingIncomeLoss": _concept(4_355_000_000, end="2025-12-31", filed="2026-01-29"),
        "DepreciationAndAmortization": _concept(1_636_003_000, end="2017-12-31", filed="2018-02-23"),
        "Depreciation": _concept(5_030_000_000, end="2025-12-31", filed="2026-01-29"),
    })
    assert c.ebitda == 9_385_000_000
