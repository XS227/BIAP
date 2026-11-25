import os, re, sys, json, statistics, collections, datetime
sys.path.insert(0, "/home/ubuntu/biap-fixplan-wt/analysis")
from global_markets import decision_overlay as do
from global_markets.analysis_ledger import AnalysisLedger, ledger_path
from openpyxl import Workbook
MARKETS = [("US", [("US", "NASDAQ"), ("US", "NYSE")], {"USD"}), ("UK", [("GB", "LSE")], {"GBP", "GBX", "GBp"}), ("DE", [("DE", "XETRA"), ("DE", "FRANKFURT")], {"EUR"}),
           ("FR", [("FR", "EURONEXT_PARIS")], {"EUR"}), ("IT", [("IT", "EURONEXT_MILAN")], {"EUR"}), ("ES", [("ES", "BME_MADRID")], {"EUR"}),
           ("NL", [("NL", "EURONEXT_AMSTERDAM")], {"EUR"}), ("SE", [("SE", "NASDAQ_STOCKHOLM")], {"SEK"}), ("NO", [("NO", "EURONEXT_OSLO")], {"NOK"}), ("FI", [("FI", "NASDAQ_HELSINKI")], {"EUR"})]
TIERS = ["BUY", "ACCUMULATE", "HOLD", "REDUCE", "SELL"]
now = datetime.datetime.now(datetime.timezone.utc)
wb = Workbook(); wb.remove(wb.active)
summary = wb.create_sheet("0 summary")
summary.append(["market", "discovered", "ranked", "BUY", "ACCUMULATE", "HOLD", "REDUCE", "SELL", "NO_REC", "BLOCK", "statements complete (strict) %", "tier-ready (core+valuation) %", "mean field coverage %", "price ≤3 days %", "median price age (days)", "BUY/ACC without P/E", "main blocker"])
samples = wb.create_sheet("1 samples (3 per market)")
samples.append(["market", "ticker", "name", "tier", "rank", "price", "currency (price)", "reporting currency", "P/E", "P/B", "market cap", "price×shares ≈ cap?", "price observed", "price age (days)", "fundamental period age (days)", "net margin", "analysed at", "automatic checks"])
age_re = re.compile(r"priceAgeDays=([0-9.]+)"); fage_re = re.compile(r"fundamentalPeriodAgeDays=([0-9.]+)")
def f(x, d=2):
    try: return None if x is None else round(float(x), d)
    except (TypeError, ValueError): return None
all_blockers = {}
for mk, exchanges, ccy in MARKETS:
    ws = wb.create_sheet(mk); ws.append(["exchange", "discovered", "ranked", *TIERS, "NO_REC", "BLOCK", "statements complete (strict) %", "tier-ready (core+valuation) %", "mean field coverage %", "price ≤3 days %", "median price age (d)", "max price age (d)", "last analysed", "main blocker"])
    nope = 0; tr_n = 0; cov_sum = 0.0; tot = collections.Counter(); blockers_all = collections.Counter(); ages_all = []; comp_n = comp_d = 0; picks = []
    for country, ex in exchanges:
        if not ledger_path(country, ex).exists(): ws.append([f"{country}:{ex}", "no ledger"]); continue
        view = do.market_view(country, ex)
        led = AnalysisLedger(country, ex)
        try:
            rows = led.summaries(limit=100000); ev = led.evidence_rows()
            import sqlite3
            con = sqlite3.connect(str(ledger_path(country, ex))); con.row_factory = sqlite3.Row
            frows = [json.loads(r[0]) for r in con.execute("select financial from ledger where in_universe=1") if r[0]]; disc = con.execute("select count(*) from ledger where in_universe=1").fetchone()[0]; con.close()
            comp = sum(1 for x in frows if x.get("complete")); tier_ready = sum(1 for x in frows if x.get("coreComplete") and x.get("valuationComplete")); cov_mean = statistics.mean([x.get("coveragePct", 0) for x in frows]) if frows else 0
            ages = [float(m.group(1)) for (_, _, why, _) in ev.values() if why and (m := age_re.search(why))]
            last = max([v[0] for v in ev.values() if v[0]] or [""])
            results = {r["ticker"]: r for r in led.full_results()}
        finally: led.close()
        c = collections.Counter(); blockers = collections.Counter()
        for t, item in view.items():
            tier = item["tier"]; gate = (item.get("blockingGate") or {}).get("label") or item.get("blockedBy")
            if tier in ("BUY", "ACCUMULATE") and (results.get(t, {}).get("company") or {}).get("pe") is None: nope += 1
            if tier == "NO_RECOMMENDATION":
                c["BLOCK" if "hard_block" in (item.get("flags") or []) else "NO_REC"] += 1
                blockers[gate or "no gate recorded"] += 1
            else: c[tier] += 1
        ranked = sum(1 for i in view.values() if i.get("rank") is not None)
        ws.append([f"{country}:{ex}", disc, ranked, *[c[t] for t in TIERS], c["NO_REC"], c["BLOCK"], f"{100*comp/disc:.0f}" if disc else None, f"{100*tier_ready/disc:.0f}" if disc else None, f"{cov_mean:.0f}",
                   f"{100*sum(1 for a in ages if a <= 3)/len(ages):.0f}" if ages else None, f(statistics.median(ages) if ages else None, 1), f(max(ages) if ages else None, 1), last[:16],
                   "; ".join(f"{k} ({v})" for k, v in blockers.most_common(2))])
        tot.update({"disc": disc, "ranked": ranked, **{t: c[t] for t in TIERS}, "NO_REC": c["NO_REC"], "BLOCK": c["BLOCK"]}); blockers_all.update(blockers); ages_all += ages; comp_n += comp; comp_d += disc; tr_n += tier_ready; cov_sum += cov_mean * disc
        for t, item in sorted(((t, i) for t, i in view.items() if i.get("rank") is not None), key=lambda x: x[1]["rank"])[:40]:
            if item["tier"] in ("BUY", "ACCUMULATE") and len([p for p in picks if p[0] == ex]) < 3 and t in results: picks.append((ex, t, item, results[t], country))
        if len([p for p in picks if p[0] == ex]) < 3:
            for t, item in sorted(((t, i) for t, i in view.items() if i.get("rank") is not None), key=lambda x: x[1]["rank"]):
                if len(picks) >= 3 * (1 + exchanges.index((country, ex))) and len([p for p in picks if p[0] == ex]) >= 3: break
                if t in results and not any(p[1] == t for p in picks): picks.append((ex, t, item, results[t], country))
    ws.append([]); ws.append(["blockers (all exchanges)", ""]); [ws.append([k, v]) for k, v in blockers_all.most_common(8)]
    main = "; ".join(f"{k} ({v})" for k, v in blockers_all.most_common(2)) or "none"
    summary.append([mk, tot["disc"], tot["ranked"], *[tot[t] for t in TIERS], tot["NO_REC"], tot["BLOCK"], f"{100*comp_n/comp_d:.0f}" if comp_d else None, f"{100*tr_n/comp_d:.0f}" if comp_d else None, f"{cov_sum/comp_d:.0f}" if comp_d else None, f"{100*sum(1 for a in ages_all if a <= 3)/len(ages_all):.0f}" if ages_all else None, f(statistics.median(ages_all) if ages_all else None, 1), nope, main])
    all_blockers[mk] = blockers_all
    # samples: first 3 distinct tickers of this market
    seen = []
    for ex, t, item, r, country in picks:
        if t in seen or len(seen) >= 3: continue
        seen.append(t); co = r.get("company") or {}; evd = r.get("evidence") or {}; why = evd.get("reasoning") or ""
        price, shares, cap, pe = f(co.get("price"), 4), f(co.get("shares_outstanding"), 0), f(co.get("market_cap"), 0), f(co.get("pe"))
        checks = []
        cur = r.get("currency") or co.get("currency")
        if cur not in ccy: checks.append(f"currency {cur} unexpected for {mk}")
        if pe is not None and (pe <= 0 or pe > 200): checks.append(f"P/E {pe} out of range")
        ratio = None
        if price and shares and cap:
            ratio = price * shares / cap
            if not 0.5 <= ratio <= 2.0: checks.append(f"price×shares/market cap = {ratio:.2f}")
        pa = age_re.search(why); fa = fage_re.search(why)
        if pa and float(pa.group(1)) > 5: checks.append(f"price {pa.group(1)} days old")
        if fa and float(fa.group(1)) > 548: checks.append(f"fundamentals {fa.group(1)} days old")
        nm = None
        for k in co:
            if "net_margin" in k or k in ("profit_margin", "net_profit_margin"): nm = f(co[k]); 
        if nm is not None and abs(nm) > 100 and abs(nm) > 1: checks.append(f"net margin {nm}")
        rc = co.get("reporting_currency"); eps = f(co.get("eps"), 4)
        if rc and cur and rc != cur and pe and eps and price:
            fx = price / (pe * eps)  # implied price-currency units per reporting-currency unit
            plaus = {("NOK", "USD"): (8, 14), ("SEK", "EUR"): (9, 13), ("GBP", "USD"): (0.6, 0.95), ("NOK", "EUR"): (10, 13), ("SEK", "USD"): (8, 13), ("GBP", "EUR"): (0.75, 1.05),
                     ("USD", "EUR"): (0.7, 1.1), ("EUR", "USD"): (0.8, 1.4), ("EUR", "GBP"): (0.75, 1.0), ("USD", "GBP"): (1.1, 1.6), ("EUR", "SEK"): (9, 13), ("EUR", "NOK"): (9, 13), ("USD", "NOK"): (8, 14), ("USD", "SEK"): (8, 13)}
            lo_hi = plaus.get((cur, rc))
            if lo_hi is None: checks.append(f"cross-currency P/E {rc}->{cur}: pair not in plausibility table (implied FX {fx:.3f})")
            elif not lo_hi[0] <= fx <= lo_hi[1]: checks.append(f"P/E NOT converted correctly: implied FX {fx:.3f} outside {lo_hi} for {rc}->{cur}")
            else: checks.append(f"info: P/E converted {rc}->{cur} (implied FX {fx:.3f}, plausible)")
        if item.get("tier") in ("BUY", "ACCUMULATE") and pe is None: checks.append("BUY/ACCUMULATE without P/E (EPS missing)")
        samples.append([mk, t, r.get("name"), item["tier"], item.get("rank"), price, cur, co.get("reporting_currency"), pe, f(co.get("pb")), cap, None if ratio is None else round(ratio, 2), str(co.get("price_observed_at"))[:16],
                        pa.group(1) if pa else None, fa.group(1) if fa else None, nm, str(item.get("analyzedAt"))[:16], "; ".join(checks) or "none found"])
    # BUY/ACC rows lacking P/E across the whole market

out = sys.argv[1]; wb.save(out); print("saved", out)
for row in summary.iter_rows(values_only=True): print(row)
