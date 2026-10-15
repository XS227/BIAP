"""End-to-end agent regression against a running BIAP Global API (read-only analyze calls).

usage: agent_regression.py OUT.json [BASE_URL] [PER_MARKET]
Per market (every ledger in /var/lib/biap-global/analysis-ledger) it picks the most liquid COMPLETE
evidence-PASS names, one COMPLETE financial (bank/insurer) if any, and one non-COMPLETE row, then
checks structural/decision invariants for the six scoring agents and Agents 8, 9, 10.
"""
import glob, json, os, sqlite3, sys, urllib.request, collections

out = sys.argv[1]
base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8091"
per_market = int(sys.argv[3]) if len(sys.argv) > 3 else 3
LEDGERS = "/var/lib/biap-global/analysis-ledger"
SIX = {"fundamental", "risk", "forecast", "comparison", "quality", "liquidity"}
CALLS = {"BUY_CANDIDATE", "HOLD_OR_WATCH", "NO_RECOMMENDATION", "AVOID_OR_REDUCE", "SELL_CANDIDATE", "REDUCE_CANDIDATE", "BUY", "SELL", "HOLD"}
GOV = {"ACCEPT", "REVIEW", "ABSTAIN", "REJECT", "BLOCK"}


def post(path, body):
    req = urllib.request.Request(base + path, json.dumps(body).encode(), {"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def currency_map(country, exchange):
    try:
        rows = json.load(open(f"/var/lib/biap-global/universe/{country}/{exchange}.json"))["instruments"]
        return {r["ticker"]: r.get("currency") for r in rows}
    except Exception:
        return {}


def pick(path):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = c.execute("select ticker,status,evidence_status,call,priority from ledger where in_universe=1").fetchall()
    ok = sorted([r for r in rows if r[1] == "COMPLETE" and r[2] == "PASS"], key=lambda r: -(r[4] or 0))
    chosen = [r[0] for r in ok[:per_market - 1]]
    fin = [r for r in ok if r[0] not in chosen and c.execute("select 1 from ledger where ticker=? and (reason like '%bank%' or result like '%\"kind\": \"bank\"%')", (r[0],)).fetchone()]
    if fin:
        chosen.append(fin[0][0])
    bad = [r for r in rows if r[1] != "COMPLETE"]
    if bad:
        chosen.append(sorted(bad, key=lambda r: -(r[4] or 0))[0][0])
    buy = [r[0] for r in rows if r[3] == "BUY_CANDIDATE" and r[0] not in chosen][:1]
    return chosen + buy


def check(d):
    errs = []
    ev = (d.get("evidence") or {}).get("status")
    call = d.get("call")
    if call not in CALLS:
        errs.append(f"unknown call {call}")
    for key in ("score", "confidence"):
        v = d.get(key)
        if not isinstance(v, (int, float)) or not (-1.0001 <= v <= 1.0001 if key == "score" else -0.0001 <= v <= 1.0001):
            errs.append(f"{key} out of range: {v}")
    sig = d.get("signals") or []
    names = {s.get("agent") for s in sig}
    if names != SIX:
        errs.append(f"six agents mismatch: {sorted(names)}")
    for s in sig:
        if not (-1.0001 <= float(s.get("vote", 0)) <= 1.0001) or not (-0.0001 <= float(s.get("confidence", 0)) <= 1.0001):
            errs.append(f"{s.get('agent')} vote/confidence out of range")
        if not str(s.get("reasoning") or "").strip():
            errs.append(f"{s.get('agent')} empty reasoning")
    gov = d.get("governance") or {}
    if str(gov.get("action")) not in GOV:
        errs.append(f"agent8 action {gov.get('action')}")
    di = d.get("decisionIntegrity") or {}
    if di.get("finalCall") != call:
        errs.append(f"decisionIntegrity.finalCall {di.get('finalCall')} != call {call}")
    dis = d.get("distress") or {}
    if not dis.get("status"):
        errs.append("agent9 missing status")
    cs = d.get("creditScoring") or {}
    if cs.get("report_only") is not True:
        errs.append("agent10 not report_only")
    if call == "BUY_CANDIDATE":
        if ev != "PASS":
            errs.append("BUY without evidence PASS")
        if gov.get("accepted") is not True:
            errs.append("BUY not accepted by agent8")
        if dis.get("positive_block"):
            errs.append("BUY despite agent9 positive_block")
    if ev == "BLOCK" and call == "BUY_CANDIDATE":
        errs.append("BUY under evidence BLOCK")
    return errs


results = {}
summary = collections.Counter()
for f in sorted(glob.glob(LEDGERS + "/*.sqlite3")):
    market = os.path.basename(f)[:-8]
    country, exchange = market.split("__", 1)
    cur = currency_map(country, exchange)
    for t in pick(f):
        key = f"{market}:{t}"
        try:
            d = post("/global/analyze", {"country": country, "exchange": exchange, "ticker": t, "currency": cur.get(t) or "USD"})
            errs = check(d)
            results[key] = {"call": d.get("call"), "evidence": (d.get("evidence") or {}).get("status"), "agent8": (d.get("governance") or {}).get("action"),
                            "agent9": (d.get("distress") or {}).get("status"), "agent10": (d.get("creditScoring") or {}).get("status", "")[:40], "errors": errs}
        except Exception as ex:  # a tool error is a failure, never silently skipped
            errs = [f"exception {type(ex).__name__}: {str(ex)[:120]}"]
            results[key] = {"errors": errs}
        summary["ok" if not errs else "fail"] += 1
        if errs:
            print("FAIL", key, errs, flush=True)
json.dump({"summary": dict(summary), "results": results}, open(out, "w"), indent=1)
print(dict(summary), "markets", len({k.split(":")[0] for k in results}))
