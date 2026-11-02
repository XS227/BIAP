"""P1.4: peer-benchmark validity. Reproduces the Equinor / Aker BP (quarterly window) and SAP (undated peers) failures under
v1 and pins the v2 behaviour: peers are kept at a partial freshness discount instead of dropping the benchmark."""
import pytest

from global_markets import freshness as fr
from global_markets.core_agents import comparison_agent
from global_markets.service import _derive_metrics
from tests.test_freshness_model import NOW, _seed
from tests.test_global_governance_agent import _company

# A quarterly-regime peer set whose latest report is 122 days old: the next interim window is open today
# (period end + 92 d + 20 d <= today <= period end + 92 d + 60 d), the same situation as Oslo on 2026-11-02.
OPEN_WINDOW_AGE_DAYS = 122


def _norway(tmp_path, monkeypatch, **kw):
    return _seed(tmp_path, monkeypatch, country="NO", exchange="EURONEXT_OSLO", base_age_h=1.0, period_age_days=OPEN_WINDOW_AGE_DAYS, **kw)


def _equinor():
    return _company(country="NO", exchange="EURONEXT_OSLO", currency="NOK", ticker="EQNR", name="Equinor", sector="Tech", pe=22.2)


# ---- reproducers: v1 (frozen) ----------------------------------------------------------------------------------------------

def test_v1_quarterly_window_discards_the_whole_benchmark(tmp_path, monkeypatch):
    _, wrapper = _norway(tmp_path, monkeypatch)
    verdict = fr.evaluate(wrapper, "NO", NOW)
    filing = verdict["dimensions"]["filing"]
    assert not verdict["usable"] and filing["state"] == "STALE"
    assert filing["excludedPct"] == 100.0 and set(filing["reasons"].values()) == {"filing_may_have_changed"}


def test_v1_equinor_comparison_abstains_with_the_misleading_message(tmp_path, monkeypatch):
    _norway(tmp_path, monkeypatch)
    enriched = _derive_metrics(_equinor())
    assert enriched.raw_provider_fields["peer_scan_cache_state"] == "scan_cache_stale"
    signal = comparison_agent(enriched)
    assert enriched.sector_pe is None and signal.vote == 0.0 and signal.confidence == 0.25
    assert "fewer than 3 same-sector peers" in signal.reasoning        # false: 50 Tech peers exist (documented defect)


def test_v1_undated_german_peers_make_the_benchmark_undetermined(tmp_path, monkeypatch):
    _, wrapper = _seed(tmp_path, monkeypatch, country="DE", exchange="XETRA", base_age_h=1.0, with_period=False)
    filing = fr.evaluate(wrapper, "DE", NOW)["dimensions"]["filing"]
    assert filing["state"] == "UNDETERMINED" and filing["undatedPct"] == 100.0


# ---- v2 --------------------------------------------------------------------------------------------------------------------

@pytest.fixture()
def v2(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")


def test_v2_keeps_peers_with_a_possibly_newer_report_and_reports_the_discount(tmp_path, monkeypatch, v2):
    _, wrapper = _norway(tmp_path, monkeypatch)
    verdict = fr.evaluate(wrapper, "NO", NOW)
    filing = verdict["dimensions"]["filing"]
    assert verdict["usable"] and filing["state"] == "VALID"
    assert filing["excludedCount"] == 0 and filing["discountedPct"] == 100.0
    assert filing["freshnessFactor"] == pytest.approx(0.70)             # 1 - 0.30 x 100 %


def test_v2_undated_peers_are_kept_at_a_discount(tmp_path, monkeypatch, v2):
    _, wrapper = _seed(tmp_path, monkeypatch, country="DE", exchange="XETRA", base_age_h=1.0, with_period=False)
    filing = fr.evaluate(wrapper, "DE", NOW)["dimensions"]["filing"]
    assert filing["state"] == "VALID" and filing["undatedPct"] == 100.0 and filing["freshnessFactor"] == pytest.approx(0.70)


def test_v2_factor_scales_with_the_share_of_discounted_peers(tmp_path, monkeypatch, v2):
    _, wrapper = _norway(tmp_path, monkeypatch)
    rows = wrapper["payload"]["deepResults"]
    for r in rows[:50]:
        r["company"]["filing_period_end"] = (NOW.date()).isoformat()      # confirmed current: cannot have a newer report
    filing = fr.filing_dimension(rows, "NO", NOW.date(), NOW.date())
    assert filing["discountedPct"] == 50.0 and filing["freshnessFactor"] == pytest.approx(0.85)


def test_v2_hard_exclusions_still_drop_the_benchmark(tmp_path, monkeypatch, v2):
    _, wrapper = _norway(tmp_path, monkeypatch)
    rows = wrapper["payload"]["deepResults"]
    for r in rows[:20]:
        r["company"]["benchmark_excluded_reason"] = "restated_unvalidated"
    filing = fr.filing_dimension(rows, "NO", NOW.date(), NOW.date())
    assert filing["state"] == "STALE" and filing["excludedPct"] == 20.0


def test_v2_known_superseded_peer_is_discounted_not_removed(tmp_path, monkeypatch, v2):
    _, wrapper = _norway(tmp_path, monkeypatch)
    rows = wrapper["payload"]["deepResults"]
    for r in rows:
        r["company"]["filing_period_end"] = NOW.date().isoformat()
    filing = fr.filing_dimension(rows, "NO", NOW.date(), NOW.date(), superseded={"T3": "2099-01-01"})
    assert filing["excludedCount"] == 0 and filing["discountReasons"] == {"T3": "filing_may_have_changed"}


def test_v2_equinor_gets_a_peer_comparison_with_discounted_confidence(tmp_path, monkeypatch, v2):
    _norway(tmp_path, monkeypatch)
    enriched = _derive_metrics(_equinor())
    assert enriched.raw_provider_fields["peer_scan_cache_state"] == "ok"
    assert enriched.sector_pe is not None and enriched.raw_provider_fields["peer_benchmark_freshness_factor"] == pytest.approx(0.70)
    signal = comparison_agent(enriched)
    assert signal.confidence == pytest.approx(0.455)
    assert "fewer than 3" not in signal.reasoning and "confidence x0.70" in signal.reasoning


def test_v2_fully_fresh_benchmark_keeps_full_confidence(tmp_path, monkeypatch, v2):
    _seed(tmp_path, monkeypatch, country="NO", exchange="EURONEXT_OSLO", base_age_h=1.0, period_age_days=30)
    enriched = _derive_metrics(_equinor())
    signal = comparison_agent(enriched)
    assert "peer_benchmark_freshness_factor" not in enriched.raw_provider_fields or enriched.raw_provider_fields["peer_benchmark_freshness_factor"] == 1.0
    assert signal.confidence == 0.65


def test_v2_message_names_the_real_cause_when_the_benchmark_is_unusable(tmp_path, monkeypatch, v2):
    _, wrapper = _norway(tmp_path, monkeypatch)
    for r in wrapper["payload"]["deepResults"][:40]:
        r["company"]["benchmark_excluded_reason"] = "restated_unvalidated"
    from global_markets.source_cache import write_json_atomic
    write_json_atomic(tmp_path / "scan-cache/NO/EURONEXT_OSLO.json", wrapper)
    signal = comparison_agent(_derive_metrics(_equinor()))
    assert signal.vote == 0.0
    assert "peer benchmark not trusted" in signal.reasoning and "fewer than 3" not in signal.reasoning


def test_v2_keeps_the_original_message_when_there_really_are_fewer_than_three_peers(tmp_path, monkeypatch, v2):
    _norway(tmp_path, monkeypatch)
    company = _company(country="NO", exchange="EURONEXT_OSLO", currency="NOK", ticker="EQNR", name="Equinor", sector="Rare Sector", pe=22.2)
    signal = comparison_agent(_derive_metrics(company))
    assert signal.vote == 0.0 and "fewer than 3 same-sector peers" in signal.reasoning


# ---- P1.4b: linear comparison vote (v2) ----------------------------------------------------------------------------------

def _vote(discount_pct, monkeypatch, version):
    from global_markets.core_agents import comparison_agent
    monkeypatch.setenv("DECISION_LOGIC_VERSION", version)
    company = _company(country="DE", exchange="XETRA", currency="EUR", ticker="X", name="X", sector="Tech", pe=100.0 - discount_pct)
    company.sector_pe = 100.0
    return comparison_agent(company).vote


@pytest.mark.parametrize("d,expected", [(10, 0.2), (-10, -0.2), (20, 0.4), (-20, -0.4), (30, 0.6), (60, 0.6),
                                        (-25, -0.5), (-40, -0.5), (-60, -0.5), (0, 0.0)])
def test_v2_comparison_vote_is_linear_with_v1_caps(d, expected, monkeypatch):
    assert _vote(d, monkeypatch, "v2") == pytest.approx(expected)


def test_v2_comparison_vote_is_monotonic_and_has_no_jump(monkeypatch):
    votes = [_vote(d / 2, monkeypatch, "v2") for d in range(-140, 141)]
    assert all(b >= a for a, b in zip(votes, votes[1:]))
    assert max(abs(b - a) for a, b in zip(votes, votes[1:])) <= 0.0101   # step of 0.5 pp x 0.02


def test_v1_comparison_vote_ladder_is_unchanged(monkeypatch):
    assert [_vote(d, monkeypatch, "v1") for d in (10, 14.9, 15, 20, 30, 60, -10, -15, -20, -30, -60)] == \
           [0.0, 0.0, 0.35, 0.35, 0.6, 0.6, 0.0, -0.3, -0.3, -0.5, -0.5]
