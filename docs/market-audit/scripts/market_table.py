"""Per-market coverage table from the persistent ledgers + universe + sector reference.
usage: market_table.py OUT.json [SECTOR_ENTRIES_BEFORE.json]"""
import collections, glob, json, os, re, sqlite3, sys
D = "/var/lib/biap-global"
out = sys.argv[1]
before_path = sys.argv[2] if len(sys.argv) > 2 else None
after = json.load(open(f"{D}/sector-reference/entries.json"))["entries"]
before = json.load(open(before_path))["entries"] if before_path else after
rows_out = {}


def sector_cov(country, exchange, entries):
    try:
        rows = json.load(open(f"{D}/universe/{country}/{exchange}.json"))["instruments"]
    except Exception:
        return None
    if not rows:
        return None
    n = sum(1 for r in rows if str(r.get("sector") or "").strip() or (entries.get(str(r.get("isin") or "").upper()) or {}).get("sector"))
    return round(100.0 * n / len(rows), 1)


def bucket(reason):
    r = (reason or "")
    if "no_usable_market_quote" in r: return "no usable quote"
    if "no official financial-statement source" in r: return "no official statement source"
    if "primary fundamentals unavailable" in r: return "official filing not found"
    if "days old" in r: return "stale official filing"
    if "core_figures" in r: return "core figures not tagged"
    if r.startswith("gate_failed"): return "gate failed"
    return r[:30] or "other"


for f in sorted(glob.glob(f"{D}/analysis-ledger/*.sqlite3")):
    m = os.path.basename(f)[:-8]
    country, exchange = m.split("__", 1)
    c = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
    rows = c.execute("select status,in_universe,call,evidence_status,financial,reason,quote from ledger").fetchall()
    u = [r for r in rows if r[1]]
    ev = collections.Counter(r[3] for r in u)
    complete = [r for r in u if r[0] == "COMPLETE"]
    core = 0
    for r in complete:
        try:
            core += 1 if json.loads(r[4]).get("coreComplete") else 0
        except Exception:
            pass
    bl = collections.Counter(bucket(r[5]) for r in u if r[0] != "COMPLETE" or r[3] != "PASS")
    rows_out[m] = {
        "discovered": len(rows), "inUniverse": len(u), "deepAnalyzed": len(complete), "verifiedCoreFundamentals": core,
        "evidencePASS": ev.get("PASS", 0), "evidenceWARN": ev.get("WARN", 0), "evidenceBLOCK": ev.get("BLOCK", 0),
        "buyCandidates": sum(1 for r in u if r[2] == "BUY_CANDIDATE"),
        "sectorCoveragePctBefore": sector_cov(country, exchange, before), "sectorCoveragePctAfter": sector_cov(country, exchange, after),
        "topBlockers": bl.most_common(3),
    }
json.dump(rows_out, open(out, "w"), indent=1)
hdr = "| Market | Discovered | In universe | Deep (COMPLETE) | Core fundamentals verified | PASS | WARN | BLOCK | BUY cand. | Sector cov. before→after | Top blockers |\n|---|---|---|---|---|---|---|---|---|---|---|"
lines = [hdr]
for m, v in rows_out.items():
    sc = "n/a" if v["sectorCoveragePctAfter"] is None else (f"{v['sectorCoveragePctBefore']}→{v['sectorCoveragePctAfter']}%" if v["sectorCoveragePctBefore"] != v["sectorCoveragePctAfter"] else f"{v['sectorCoveragePctAfter']}%")
    bl = "; ".join(f"{k} {n}" for k, n in v["topBlockers"]) or "-"
    lines.append(f"| {m.replace('__', ' / ')} | {v['discovered']} | {v['inUniverse']} | {v['deepAnalyzed']} | {v['verifiedCoreFundamentals']} | {v['evidencePASS']} | {v['evidenceWARN']} | {v['evidenceBLOCK']} | {v['buyCandidates']} | {sc} | {bl} |")
print("\n".join(lines))
