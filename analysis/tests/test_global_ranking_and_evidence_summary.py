"""Regression tests for the 2026-10-13 US/GB audit (ranking basis, evidence denominator, LSE preference lines)."""
from global_markets.lse_official import _ordinary_row, non_ordinary_description
from global_markets.scanner import GlobalMarketScanner


def _buy(ticker, score, confidence):
    return {
        "country": "US", "exchange": "NASDAQ", "ticker": ticker, "call": "BUY_CANDIDATE",
        "evidence": {"status": "PASS"}, "score": score, "confidence": confidence,
    }


def test_ranking_is_score_times_confidence_and_raw_score_rank_is_explicit():
    # Live NASDAQ 2026-10-13: ASML has the highest raw score but lower confidence than GOOGL.
    rows = [_buy("ASML", 0.430661, 0.630616), _buy("GOOGL", 0.417646, 0.696134), _buy("MSFT", 0.395447, 0.696134)]
    ranked = GlobalMarketScanner.annotate_ranking(GlobalMarketScanner._recommendations(rows, 10), rows)
    assert [r["ticker"] for r in ranked] == ["GOOGL", "MSFT", "ASML"]
    assert [r["rank"] for r in ranked] == [1, 2, 3]
    assert {r["rankCriterion"] for r in ranked} == {"score_x_confidence"}
    by = {r["ticker"]: r for r in ranked}
    assert by["ASML"]["rawScoreRank"] == 1 and by["GOOGL"]["rawScoreRank"] == 2
    assert by["GOOGL"]["rankScore"] > by["ASML"]["rankScore"]


def test_annotate_ranking_does_not_mutate_inputs():
    rows = [_buy("A", 0.5, 0.5)]
    GlobalMarketScanner.annotate_ranking(rows, rows)
    assert "rank" not in rows[0]


def test_evidence_summary_uses_ledger_counts_not_payload_rows():
    summary = GlobalMarketScanner.evidence_summary(
        {"deepAnalyzed": 3001, "evidencePass": 2806, "evidenceWarn": 0, "evidenceBlock": 195, "payloadRowsShown": 150}
    )
    assert summary["denominator"] == 3001
    assert summary["pass"] + summary["warn"] + summary["block"] == summary["denominator"]
    assert summary["basis"] == "ledger_all_deep_analyzed"


def test_lse_preference_lines_are_not_ordinary_equity():
    base = {"category": "EQUITY", "currency": "GBP", "isin": "GB0007548133", "tidm": "91ID", "maturitydate": None}
    for text in (
        "NATWEST GROUP PLC 11% CUM NON-RED PRF GBP1",
        "BP PLC 8% CUM 1ST PRF #1",
        "SANTANDER UK PLC 10 3/8% NON-CUM STLG PRF SHS #1",
        "FISHGUARD & ROSSLARE RLYS & HBRS CO 3 1/2% GTD PRF STK",
        "CITY OF LONDON INVESTMENT TRUST PLC PFD ORD STK(14% NON-CUM)",
    ):
        assert non_ordinary_description(text), text
        assert not _ordinary_row({**base, "description": text}), text


def test_lse_ordinary_shares_still_accepted():
    base = {"category": "EQUITY", "currency": "GBX", "isin": "GB00B1YW4409", "tidm": "III", "maturitydate": None}
    for text in ("3I GROUP PLC ORD 73 19/22P", "SHELL PLC ORD EUR0.07", "CUMBRIA TRAVEL PLC ORD 1P", "LAW DEBENTURE CORPORATION PLC ORD 5P"):
        assert not non_ordinary_description(text), text
        assert _ordinary_row({**base, "description": text}), text


def test_cached_gb_snapshot_drops_legacy_preference_rows_and_adjusts_discovered_count(tmp_path):
    from global_markets.cached_universe import PersistentUniverseProvider
    from global_markets.models import GlobalCompany, SourceEvidence
    from global_markets.providers import InstrumentUniverseProvider

    def company(ticker, name, isin, desc):
        return GlobalCompany(
            country="GB", exchange="LSE", currency="GBP", ticker=ticker, name=name, mic_code="XLON", isin=isin,
            raw_provider_fields={"official_universe": True, "trusted_official_equity": True, "lse_description": desc},
            sources=[SourceEvidence(provider="fake", source_type="instrument_reference", quality=0.9)],
        )

    class Upstream(InstrumentUniverseProvider):
        provider_id = "fake-lse"

        def list_instruments(self, *, country=None, exchange=None):
            return [
                company("III", "3I GROUP PLC", "GB00B1YW4409", "3I GROUP PLC ORD 73 19/22P"),
                company("SAN", "SANTANDER UK PLC", "GB0000000002", "SANTANDER UK PLC 10 3/8% NON-CUM STLG PRF SHS #1"),
                company("BPA", "BP PLC", "GB0000000003", "BP PLC 8% CUM 1ST PRF #1"),
            ]

    provider = PersistentUniverseProvider(Upstream(), data_dir=str(tmp_path), fresh_hours=12)
    rows = list(provider.list_instruments(country="GB", exchange="LSE"))
    assert [r.ticker for r in rows] == ["III"]
    info = provider.snapshot_info(country="GB", exchange="LSE")
    assert info["officialCount"] == 1 and info["resolvedCount"] == 1
