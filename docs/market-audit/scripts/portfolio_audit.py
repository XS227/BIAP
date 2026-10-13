"""Portfolio optimizer audit against a running API: cap enforcement, exposure, residual-cash explanation.
usage: portfolio_audit.py INSTRUMENTS.json OUT.json [BASE_URL]"""
import json, sys, urllib.request, collections
inst = json.load(open(sys.argv[1]))
out = sys.argv[2]
base = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8091"
SCEN = {
    "default10": {"maxPositions": 10},
    "wide20": {"maxPositions": 20},
    "sector20": {"maxPositions": 15, "maxSectorPct": 20},
    "country25": {"maxPositions": 15, "maxCountryPct": 25},
    "tight": {"maxPositions": 8, "maxPositionPct": 8, "maxCountryPct": 20, "maxSectorPct": 20},
    "de_only": {"maxPositions": 10, "allowedCountries": ["DE"]},
    "eu_small": {"maxPositions": 10, "allowedCountries": ["NL", "FI", "ES", "IT"]},
    "cash0": {"maxPositions": 20, "minCashReservePct": 0, "maxPositionPct": 8},
}


def run(extra, insts):
    profile = {"capital": 100000, "baseCurrency": "USD", **extra}
    req = urllib.request.Request(base + "/global/portfolio", json.dumps({"profile": profile, "instruments": insts}).encode(), {"content-type": "application/json"})
    return profile, json.load(urllib.request.urlopen(req, timeout=900))


results = {}
for name, extra in SCEN.items():
    insts = inst if "allowedCountries" not in extra else inst
    profile, d = run(extra, insts)
    p = d["proposal"]
    sector_of = {}
    for a in d["analyses"]:
        c = a.get("company") or {}
        sector_of[a.get("identity") or f"{a.get('country')}:{a.get('ticker')}"] = c.get("sector")
    by_t = {(a.get("ticker")): (a.get("company") or {}).get("sector") for a in d["analyses"]}
    sec, ctry = collections.defaultdict(float), collections.defaultdict(float)
    for al in p["allocations"]:
        sec[by_t.get(al["ticker"]) or "UNKNOWN"] += al["weight_pct"]
        ctry[al["country"]] += al["weight_pct"]
    ms, mc, mp = profile.get("maxSectorPct", 30), profile.get("maxCountryPct", 40), profile.get("maxPositionPct", 10)
    mincash = profile.get("minCashReservePct", 10)
    errs = []
    if any(v > ms + 0.01 for v in sec.values()):
        errs.append(f"sector cap {ms} exceeded {dict(sec)}")
    if any(v > mc + 0.01 for v in ctry.values()):
        errs.append(f"country cap {mc} exceeded {dict(ctry)}")
    if any(a["weight_pct"] > mp + 0.01 for a in p["allocations"]):
        errs.append("position cap exceeded")
    if p["cash_pct"] < mincash - 0.01:
        errs.append(f"cash {p['cash_pct']} below reserve {mincash}")
    if len(p["allocations"]) > profile["maxPositions"]:
        errs.append("too many positions")
    if abs(p["invested_pct"] + p["cash_pct"] - 100) > 0.05:
        errs.append("invested+cash != 100")
    resid = round(100 - mincash - p["invested_pct"], 2)
    rej = collections.Counter(r["constraint"] for r in p["rejections"])
    results[name] = {"positions": len(p["allocations"]), "invested_pct": p["invested_pct"], "cash_pct": p["cash_pct"], "unexplained_residual_pct": resid,
                     "reasoning": p.get("reasoning"), "maxSector": max(sec.values() or [0]), "maxCountry": max(ctry.values() or [0]),
                     "unknownSector_pct": sec.get("UNKNOWN", 0), "rejections": dict(rej), "errors": errs}
    print(name, {k: v for k, v in results[name].items() if k not in ("reasoning",)}, flush=True)
json.dump(results, open(out, "w"), indent=1)
