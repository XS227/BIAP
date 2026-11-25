#!/usr/bin/env python3
"""Summarise two outputs of p1_12_liquidity_measure.py (asis, abstain) as markdown tables on stdout."""
import json, sys, statistics as st, collections
a, b = (json.load(open(p)) for p in sys.argv[1:3])
TIERS = ["BUY", "ACCUMULATE", "HOLD", "REDUCE", "SELL", "NO_RECOMMENDATION"]
groups = {"US": ["US:NASDAQ", "US:NYSE"], "DE": ["DE:XETRA"], "NO": ["NO:EURONEXT_OSLO"]}
def spearman(x, y):
    n = len(x)
    if n < 3: return float("nan")
    rx = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: x[i]))}
    ry = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: y[i]))}
    mx = (n - 1) / 2
    num = sum((rx[i] - mx) * (ry[i] - mx) for i in range(n)); den = sum((rx[i] - mx) ** 2 for i in range(n))
    return num / den
print("## 1. Liquidity vote distribution (stored vote, rows with a liquidity signal and confidence > 0)\n")
print("| Market | rows | with liq. data | vote = +0.42 | vote >= +0.40 | vote > 0 | vote = 0 | vote < 0 |\n|---|---|---|---|---|---|---|---|")
for g, ms in groups.items():
    rows = [t for m in ms for t in a["markets"][m]["tickers"].values()]
    d = [t for t in rows if t.get("liqVote") is not None and (t.get("liqConf") or 0) > 0]
    n = max(len(d), 1)
    f = lambda c: f"{c} ({100*c/n:.1f}%)"
    print(f"| {g} | {len(rows)} | {len(d)} | {f(sum(abs(t['liqVote']-0.42)<0.005 for t in d))} | {f(sum(t['liqVote']>=0.40 for t in d))} | {f(sum(t['liqVote']>0 for t in d))} | {f(sum(t['liqVote']==0 for t in d))} | {f(sum(t['liqVote']<0 for t in d))} |")
print("\nVote values (rounded 2 dp), top 6 per group:")
for g, ms in groups.items():
    d = [round(t["liqVote"], 2) for m in ms for t in a["markets"][m]["tickers"].values() if t.get("liqVote") is not None and (t.get("liqConf") or 0) > 0]
    print(f"- {g}: " + ", ".join(f"{v:+.2f}: {c}" for v, c in collections.Counter(d).most_common(6)))
print("\n## 2. v2 with liquidity removed from the direction (weights re-normalised) vs v2 as is\n")
print("Tier counts (as is -> without liquidity vote):\n\n| Market | " + " | ".join(TIERS) + " |\n|---|" + "---|" * len(TIERS))
for g, ms in groups.items():
    for m in ms:
        ca, cb = a["markets"][m]["tierCounts"], b["markets"][m]["tierCounts"]
        print(f"| {m} | " + " | ".join(f"{ca.get(t,0)} -> {cb.get(t,0)}" for t in TIERS) + " |")
print("\nScore / rank / tier movement (tickers with a score in both runs):\n")
print("| Market | n | median abs score change | max abs | Spearman rank corr | tier changed | BUY<->other | SELL<->other |\n|---|---|---|---|---|---|---|---|")
for g, ms in groups.items():
    for m in ms:
        A, B = a["markets"][m]["tickers"], b["markets"][m]["tickers"]
        ks = [k for k in A if k in B and A[k].get("score") is not None and B[k].get("score") is not None]
        d = [abs(A[k]["score"] - B[k]["score"]) for k in ks]
        rho = spearman([A[k]["score"] for k in ks], [B[k]["score"] for k in ks])
        ch = [k for k in A if k in B and A[k]["tier"] != B[k]["tier"]]
        bu = sum((A[k]["tier"] == "BUY") != (B[k]["tier"] == "BUY") for k in ch)
        se = sum((A[k]["tier"] == "SELL") != (B[k]["tier"] == "SELL") for k in ch)
        print(f"| {m} | {len(ks)} | {st.median(d):.4f} | {max(d):.4f} | {rho:.4f} | {len(ch)} ({100*len(ch)/len(A):.1f}%) | {bu} | {se} |")
print("\nTier transition matrix (as is -> without liquidity), US+DE+NO pooled, only changed pairs:\n")
tr = collections.Counter()
for m in a["markets"]:
    A, B = a["markets"][m]["tickers"], b["markets"][m]["tickers"]
    for k in A:
        if k in B and A[k]["tier"] != B[k]["tier"]: tr[(A[k]["tier"], B[k]["tier"])] += 1
for (x, y), c in sorted(tr.items(), key=lambda i: -i[1]): print(f"- {x} -> {y}: {c}")
print("\nLiquidity vote of the BUYs that leave BUY / enter BUY (as is vs without):")
for m in a["markets"]:
    A, B = a["markets"][m]["tickers"], b["markets"][m]["tickers"]
    lo = [A[k]["liqVote"] for k in A if k in B and A[k]["tier"] == "BUY" and B[k]["tier"] != "BUY" and A[k].get("liqVote") is not None]
    hi = [A[k]["liqVote"] for k in A if k in B and A[k]["tier"] != "BUY" and B[k]["tier"] == "BUY" and A[k].get("liqVote") is not None]
    print(f"- {m}: left BUY {len(lo)} (mean liq vote {st.mean(lo) if lo else float('nan'):+.2f}); entered BUY {len(hi)} (mean {st.mean(hi) if hi else float('nan'):+.2f})")
print("\n## 3. Tradability gate: names failing, by threshold\n")
print("Turnover = avg 30d volume x price / market cap, in % per day (scale-free). Value = avg 30d volume x price in local currency per day.\n")
print("| Market | with volume+price+mcap | turnover<0.01% | <0.02% | <0.05% | value<25k | <100k | <500k | no volume data |\n|---|---|---|---|---|---|---|---|---|")
for g, ms in groups.items():
    rows = [t for m in ms for t in a["markets"][m]["tickers"].values()]
    ok = [t for t in rows if t.get("avgVol") and t.get("price") and t.get("mcap")]
    tov = [t["avgVol"] * t["price"] / t["mcap"] * 100 for t in ok]
    val = [t["avgVol"] * t["price"] for t in rows if t.get("avgVol") and t.get("price")]
    nov = sum(1 for t in rows if not t.get("avgVol"))
    c = lambda xs, th: f"{sum(x < th for x in xs)} ({100*sum(x < th for x in xs)/max(len(xs),1):.1f}%)"
    print(f"| {g} | {len(ok)} | {c(tov,0.01)} | {c(tov,0.02)} | {c(tov,0.05)} | {c(val,25e3)} | {c(val,1e5)} | {c(val,5e5)} | {nov} |")
print("\nIf the gate caps BUY/ACCUMULATE at HOLD for names failing (turnover < 0.02% OR value < 100k local per day), applied on top of the 'without liquidity vote' run:\n")
print("| Market | BUY capped | ACCUMULATE capped | BUY after | ACCUMULATE after |\n|---|---|---|---|---|")
for g, ms in groups.items():
    for m in ms:
        B = b["markets"][m]["tickers"]
        def fail(t):
            tv = t["avgVol"] * t["price"] / t["mcap"] * 100 if (t.get("avgVol") and t.get("price") and t.get("mcap")) else None
            vl = t["avgVol"] * t["price"] if (t.get("avgVol") and t.get("price")) else None
            return (tv is not None and tv < 0.02) or (vl is not None and vl < 1e5)
        cb = sum(1 for t in B.values() if t["tier"] == "BUY" and fail(t)); ca = sum(1 for t in B.values() if t["tier"] == "ACCUMULATE" and fail(t))
        print(f"| {m} | {cb} | {ca} | {b['markets'][m]['tierCounts']['BUY']-cb} | {b['markets'][m]['tierCounts']['ACCUMULATE']-ca} |")
