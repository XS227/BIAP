"""DE peer evidence policy options A / B / ledger corrections: isolated dry-run comparison (no production data touched).

Usage: python de_option_ab_eval.py <baseline_data_dir> <e5_out.json> <evidence_e6.json> <out.json>
  <baseline_data_dir>: an isolated COPY of the DE analysis ledgers + scan cache (data/analysis-ledger, data/scan-cache)
  <e5_out.json>:       the E5 overlay (ticker -> verified period end) = the baseline evidence state
Everything is applied in memory to rows read from the copy; nothing is written back and the gate runs are dry runs (replaced=false).

Rules (all evaluated on a row's STORED ledger values against figures printed in the issuer's own filing)
* strict (baseline, de_peer_doc_verify.decide): stored revenue > 0 -> period + revenue + net income found; stored revenue None/0 -> period + net income + EPS printed to the cent.
* A  "revenue defect": stored revenue > 0 is NOT printed, BUT period + net income + EPS (printed, to the cent) all match AND the filing prints a revenue line for the same entity
     (so the stored revenue is checkable and demonstrably differs). The row is admitted with revenue_basis = "disputed_not_used".
* B  "no-revenue shell": stored revenue is exactly 0.0, the filing's income statement has NO revenue line (non-applicable, not a reported zero), period + net income match.
     EPS is not required.
* B2 = B + the stored EPS must be exactly reproducible (to the cent) from the filing's printed net income / printed share count (a deterministic cross-check instead of "NI only").
* C  corrections: replace a stored field by the filing's printed value when the printed value is on the same line item (NI label, basic IAS 33 EPS, same revenue line) and
     unambiguous. Definition-dependent revenue (Vonovia) and bases that do not reconcile (Berliner Effektengesellschaft EPS) are NOT corrected.
"""
import copy, json, os, statistics, sys
from datetime import datetime
from pathlib import Path

ROUND_TOL = 5000.0       # the provider rounds stored statement values to 10,000 -> half-step tolerance


def near(stored, printed, tol=ROUND_TOL):
    """Match at the provider's 10,000 rounding step, capped at 2 % of the printed figure: a +-5,000 band around a 10,595 revenue
    (47 %) is no evidence, around a 292,000 net income (1.7 %) it is."""
    if stored is None or printed is None:
        return False
    return abs(stored - printed) <= min(tol, 0.02 * abs(printed))


def cents(x):
    return None if x is None else round(x + 0.0, 2)


def ni_ok(co, f):
    return f.get("net_income") is not None and near(co.get("net_income"), f["net_income"]["printed"])


def eps_printed_ok(co, f):
    e = f.get("eps")
    return bool(e) and e.get("basis_consistent_with_net_income", True) and co.get("eps") is not None and cents(abs(co["eps"])) == cents(abs(e["printed"])) and (co["eps"] < 0) == (e["printed"] < 0)


def eps_derived_ok(co, f):
    n, s = f.get("net_income"), f.get("shares")
    return bool(n and s) and co.get("eps") is not None and cents(co["eps"]) == cents(n["printed"] / s["printed"])


def rev_positive(co):
    return co.get("revenue") not in (None, 0, 0.0)


def strict(co, f):
    if not f.get("period_phrase_found"):
        return False
    if rev_positive(co):
        return bool(f.get("revenue")) and near(co["revenue"], f["revenue"]["printed"]) and ni_ok(co, f)
    return ni_ok(co, f) and eps_printed_ok(co, f)


def rule_a(co, f):
    return (f.get("period_phrase_found") and rev_positive(co) and not strict(co, f) and ni_ok(co, f) and eps_printed_ok(co, f) and f.get("revenue") is not None)


def rule_b(co, f):
    return bool(f.get("period_phrase_found") and co.get("revenue") == 0 and co.get("revenue") is not None and f.get("revenue") is None and ni_ok(co, f))


def rule_b2(co, f):
    return rule_b(co, f) and eps_derived_ok(co, f) and f["net_income"]["printed"] > 0     # positive earnings only (Z29 loss-making: not an eligible peer)


def corrections(co, f):
    """Printed-value replacements that are unambiguous; returns {field: new_value}."""
    out = {}
    r = f.get("revenue")
    if r and not r.get("definition_ambiguous") and rev_positive(co) and not near(co["revenue"], r["printed"]) and co["revenue"] == round(r["printed"] / 10000.0) * 10000.0:
        out["revenue"] = r["printed"]       # stored value is exactly the printed figure rounded to the provider's 10,000 step (same step as the net-income field)
    n = f.get("net_income")
    if n and co.get("net_income") is not None and not near(co["net_income"], n["printed"]) and "Gesamtergebnis" in n["label"]:
        out["net_income"] = n["printed"]                                # stored value is a different line (comprehensive income)
    e = f.get("eps")
    if e and e.get("basis_consistent_with_net_income") and co.get("eps") is not None and "net_income" in out:
        out["eps"] = e["printed"]
    return out


def apply_correction(co, new):
    old_eps = co.get("eps")
    for k, v in new.items():
        co[k] = v
    if "eps" in new and old_eps and co.get("pe") and co.get("pe") > 0:
        co["pe"] = co["pe"] * old_eps / new["eps"]                     # price unchanged: pe = price / eps
    return co


LIVE = os.environ.get("DE_EVAL_LIVE") == "1"    # live official post-trade quotes in memory (dry run); default = offline fixture


def main():
    base, e5p, evp, outp = sys.argv[1:5]
    os.environ.update(BIAP_GLOBAL_DATA_DIR=base, BIAP_GLOBAL_ONLINE_FIRST="1")
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "analysis"))
    from global_markets import evidence_store as es
    e5 = json.load(open(e5p)); ev = json.load(open(evp))["issuers"]
    now = datetime.fromisoformat(e5["generatedAt"])
    orig = es.read_ledger_rows

    def fixture(c, e, rows):
        d = now.date().isoformat()
        return ([{"ticker": x["company"]["ticker"], "price": x["company"].get("price") or 0, "quoteDate": d} for x in rows], [], "OFFLINE-FIXTURE")

    def run(label, flags):
        log = {}

        def patched(country, exchange, *, limit=None):
            rows = orig(country, exchange, limit=limit)
            for r in rows:
                co = r["company"]; k = f"{exchange.upper()}:{co['ticker']}"
                if k in e5["overlay"] and not co.get("filing_period_end"):
                    co["filing_period_end"] = e5["overlay"][k]
                f = ev.get(co.get("isin"))
                if not f or co.get("filing_period_end"):
                    continue
                if "C" in flags:
                    new = corrections(co, f)
                    if new:
                        apply_correction(co, new); log[co["isin"]] = {"corrected": sorted(new)}
                admitted = strict(co, f) or ("A" in flags and rule_a(co, f)) or ("B" in flags and rule_b(co, f)) or ("B2" in flags and rule_b2(co, f)) or ("Bx" in flags and (rule_b(co, f) or (co.get("revenue") is None and f.get("revenue") is None and ni_ok(co, f))))
                if admitted:
                    co["filing_period_end"] = f["period_end"]
                    log.setdefault(co["isin"], {})["dated_by"] = [n for n, ok in (("strict", strict(co, f)), ("A", rule_a(co, f)), ("B", rule_b(co, f)), ("B2", rule_b2(co, f))) if ok][:1]
            return rows
        es.read_ledger_rows = patched
        res = {"label": label, "flags": sorted(flags), "applied": log}
        try:
            for m in ("XETRA", "FRANKFURT"):
                o = (es.rebuild_from_ledger("DE", m, dry_run=True) if LIVE else es.rebuild_from_ledger("DE", m, quote_fetch=fixture, now=now, dry_run=True))
                fd = o.get("filingDimension") or {}
                members = [r["company"] for r in patched("DE", m) if (r["company"].get("pe") or 0) > 0 or (r["company"].get("pb") or 0) > 0]
                kept = [c for c in members if c["ticker"].upper() not in (fd.get("reasons") or {})]
                res[m] = {"status": o.get("status"), "members": len(members), "excluded": fd.get("excludedCount"), "excludedPct": fd.get("excludedPct"),
                          "pbRetentionPct": o.get("pbRetentionPct"), "pbRetained": len([c for c in kept if (c.get("pb") or 0) > 0]), "pbBase": len([c for c in members if (c.get("pb") or 0) > 0]),
                          "peRetentionPct": o.get("peRetentionPct"), "coveragePct": o.get("coveragePct"), "problems": o.get("problems"),
                          "medianPB": round(statistics.median([c["pb"] for c in kept if (c.get("pb") or 0) > 0]), 4), "medianPE": round(statistics.median([c["pe"] for c in kept if (c.get("pe") or 0) > 0]), 4),
                          "excludedTickers": sorted((fd.get("reasons") or {}))}
        finally:
            es.read_ledger_rows = orig
        return res

    variants = [("baseline", set()), ("A", {"A"}), ("B", {"B"}), ("B2", {"B2"}), ("A+B", {"A", "B"}), ("A+B2", {"A", "B2"}),
                ("C", {"C"}), ("C+A", {"C", "A"}), ("C+B", {"C", "B"}), ("C+B2", {"C", "B2"}), ("C+A+B", {"C", "A", "B"}), ("B-extended(+None revenue)", {"Bx"})]
    if LIVE:
        variants = [v for v in variants if v[0] in ("baseline", "C", "C+B2")]      # Monday check: baseline vs corrections vs corrections + B2 (RKB only)
    out = [run(l, f) for l, f in variants]
    json.dump(out, open(outp, "w"), indent=1, default=str)
    print(f"{'variant':26s} | XETRA excl (pct) status | FRANKFURT excl (pct) P/B ret status")
    for r in out:
        x, f = r["XETRA"], r["FRANKFURT"]
        print(f"{r['label']:26s} | {x['excluded']}/{x['members']} ({x['excludedPct']}%) {x['status']} | {f['excluded']}/{f['members']} ({f['excludedPct']}%) {f['pbRetained']}/{f['pbBase']}={f['pbRetentionPct']}% {f['status']}")


if __name__ == "__main__":
    main()
