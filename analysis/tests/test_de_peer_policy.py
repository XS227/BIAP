import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT / "docs" / "validation" / "tools"))

import de_option_ab_eval as tool  # noqa: E402
from global_markets import de_peer_policy as pol  # noqa: E402

E6 = json.load(open(ROOT / "docs" / "validation" / "DE_PEER_EVIDENCE_E6_2026-10-17.json"))["issuers"]


def row(isin, **kw):
    return {"company": {"isin": isin, "ticker": E6[isin]["ticker"], **kw}}


def rows():
    return [
        row("DE0006942808", revenue=10000.0, net_income=4850000.0, eps=0.18, pe=14.33),
        row("DE000A1TNUT7", revenue=None, net_income=26400000.0, eps=1.4, pe=13.43),
        row("DE000A2LQ2D0", revenue=0.0, net_income=-2330000.0, eps=-0.47),
        row("DE0008103102", revenue=0.0, net_income=290000.0, eps=0.34),
        row("DE000A1ML7J1", revenue=5061300000.0, net_income=3723000000.0, eps=4.39),
        row("DE0005221303", revenue=None, net_income=27340000.0, eps=2.09),
    ]


def test_registry_matches_e6_evidence_and_has_provenance():
    reg = pol.registry()
    assert set(reg) == set(E6)
    for isin, r in reg.items():
        assert r["sha256"] == E6[isin]["sha256"] and r["source_url"].startswith("https://") and r["evidenceRef"].endswith("E6_2026-10-17.json")


def test_policy_decisions_on_the_six_reviewed_issuers():
    rs = rows()
    log = pol.apply_to_rows(rs)
    by = {r["company"]["ticker"]: r["company"] for r in rs}
    assert by["PZS"]["revenue"] == 10594.89 and by["PZS"]["filing_period_end"] == "2025-12-31"
    assert by["DBAN"]["net_income"] == 24698000 and by["DBAN"]["eps"] == 1.39 and abs(by["DBAN"]["pe"] * 1.39 - 13.43 * 1.4) < 1e-9
    assert log["DE000A2LQ2D0"]["dated_by"] == "B2" and log["DE0008103102"]["dated_by"] == "B2"
    # unchanged and undated: Vonovia (definition unconfirmed), Berliner Effektengesellschaft (EPS basis mismatch)
    for t in ("VNA", "BFV"):
        assert "filing_period_end" not in by[t]
    assert by["VNA"]["revenue"] == 5061300000.0 and by["BFV"]["eps"] == 2.09


def test_rows_already_dated_are_untouched():
    r = row("DE000A1TNUT7", revenue=None, net_income=26400000.0, eps=1.4, filing_period_end="2025-12-31")
    before = copy.deepcopy(r)
    assert pol.apply_to_rows([r]) == {} and r == before


def test_b2_requires_eps_reproduction_zero_revenue_and_no_filing_revenue_line():
    f = E6["DE000A2LQ2D0"]
    assert pol.rule_b2({"revenue": 0.0, "net_income": -2330000.0, "eps": -0.47}, f)
    assert not pol.rule_b2({"revenue": 0.0, "net_income": -2330000.0, "eps": -0.50}, f)
    assert not pol.rule_b2({"revenue": None, "net_income": -2330000.0, "eps": -0.47}, f)
    assert not pol.rule_b2({"revenue": 0.0, "net_income": -2330000.0, "eps": -0.47}, E6["DE0006942808"])   # filing prints revenue


def test_parity_with_evidence_tool_rules():
    for co in [r["company"] for r in rows()]:
        f = E6[co["isin"]]
        assert pol.strict(co, f) == tool.strict(co, f)
        assert pol.rule_b2(co, f) == tool.rule_b2(co, f)
        assert pol.corrections(co, f) == tool.corrections(co, f)


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv(pol.ENV_FLAG, raising=False)
    assert not pol.enabled()
    monkeypatch.setenv(pol.ENV_FLAG, "1")
    assert pol.enabled()


def test_rebuild_hook_is_in_memory_flag_gated_and_de_only(monkeypatch, tmp_path):
    from global_markets import evidence_store as es, benchmark_refresh as br
    seen = {}

    def fake_reprice(country, exchange, **kw):
        seen["rows"] = kw["source_wrapper"]["payload"]["deepResults"]
        return {"status": "DRY_RUN_OK"}

    monkeypatch.setattr(br, "reprice_benchmark", fake_reprice)
    monkeypatch.setattr(es, "read_ledger_rows", lambda c, e, limit=None: [{"inputsAsOf": "2026-10-01T00:00:00+00:00", **r} for r in rows()])
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    monkeypatch.delenv(pol.ENV_FLAG, raising=False)
    out = es.rebuild_from_ledger("DE", "XETRA", dry_run=True)
    assert "dePeerPolicy" not in out and not any("filing_period_end" in r["company"] for r in seen["rows"])
    monkeypatch.setenv(pol.ENV_FLAG, "1")
    out = es.rebuild_from_ledger("DE", "XETRA", dry_run=True)
    assert set(out["dePeerPolicy"]) >= {"DE0006942808", "DE000A1TNUT7", "DE000A2LQ2D0", "DE0008103102"}
    out = es.rebuild_from_ledger("IT", "MIL", dry_run=True)
    assert "dePeerPolicy" not in out
