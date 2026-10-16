"""DE peer rebuild, option B: resolve exact filing period ends from AUTHORITATIVE sources, in memory, <=10 companies per batch.

Usage: python de_peer_period_resolve.py <scratch_dir> <out.json>

Safety model
* Reads production ledgers through a sqlite backup copy in <scratch_dir>; production data is never opened for writing.
* Nothing is persisted except aggregate/per-ticker outcome counts in <out.json> (no financial values).
* Period ends are taken ONLY from BIAP's reviewed issuer registries (de_issuer_esef.json, de_verified_annual_reports.json).
  They are applied to a ledger row only if the registry's stored figures match the row's own figures (revenue / net income /
  EPS within 1 %), i.e. the row provably IS that filing. Otherwise the row stays undated.
* Each candidate's official source URL is probed with a bounded HEAD request (no body download).
* Börse Frankfurt key data is year-only; Unternehmensregister is robots-disallowed; filings.xbrl.org indexes no DE filings.
  None of those is used and nothing is invented.
* Stops safely if MemAvailable < 150 MB or free disk < 3 GB.
"""
import json, os, shutil, sqlite3, sys, time, zlib
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "analysis"))
SCRATCH = Path(sys.argv[1]); OUT = Path(sys.argv[2])
DATA = SCRATCH / "data"
os.environ.update(BIAP_GLOBAL_DATA_DIR=str(DATA), BIAP_GLOBAL_ONLINE_FIRST="1")
from global_markets import evidence_store as es, freshness as fr  # noqa: E402

REG = ROOT / "analysis/global_markets/data"
PROD = Path("/var/lib/biap-global")
MARKETS = ["XETRA", "FRANKFURT"]
BATCH = 10
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def guard():
    mem = int([l for l in open("/proc/meminfo") if l.startswith("MemAvailable")][0].split()[1]) // 1024
    disk = shutil.disk_usage("/").free // 2**20
    if mem < 150 or disk < 3072:
        raise SystemExit(f"RESOURCE STOP mem_available={mem}MB disk_free={disk}MB")
    return mem, disk


def prepare():
    (DATA / "analysis-ledger").mkdir(parents=True, exist_ok=True)
    (DATA / "scan-cache/DE").mkdir(parents=True, exist_ok=True)
    for m in MARKETS:
        src = sqlite3.connect(f"file:{PROD}/analysis-ledger/DE__{m}.sqlite3?mode=ro", uri=True)
        dst = sqlite3.connect(DATA / f"analysis-ledger/DE__{m}.sqlite3"); src.backup(dst); dst.close(); src.close()
        shutil.copy2(PROD / f"scan-cache/DE/{m}.json", DATA / f"scan-cache/DE/{m}.json")


def registries():
    reg = {}
    for r in json.load(open(REG / "de_issuer_esef.json"))["issuers"]:
        reg[r["isin"]] = {"period_end": r["period_end"], "url": r["package_url"], "kind": "issuer-ESEF-registry", "fund": None}
    for r in json.load(open(REG / "de_verified_annual_reports.json"))["issuers"]:
        reg.setdefault(r["isin"], {"period_end": r["periodEnd"], "url": r["sourceUrl"], "kind": "verified-annual-report-registry",
                                   "fund": r.get("fundamentals") or {}})
    return reg


def close(a, b, tol=0.01):
    return isinstance(a, (int, float)) and isinstance(b, (int, float)) and b != 0 and abs(a - b) <= tol * abs(b)


def matches(co, fund):
    if not fund:
        return None            # ESEF registry rows carry no figures here; verified separately by the OAM provider
    hits = [close(co.get(k), fund.get(k)) for k in ("revenue", "net_income", "eps") if fund.get(k) is not None]
    return bool(hits) and all(hits)


def probe(url, client):
    try:
        r = client.head(url, follow_redirects=True, timeout=12)
        return r.status_code if r.status_code != 405 else client.get(url, headers={"Range": "bytes=0-0"}, timeout=12).status_code
    except Exception as e:
        return f"ERR:{type(e).__name__}"


def main():
    prepare(); reg = registries(); log = []
    overlay, outcome = {}, {}
    universe = {}
    for m in MARKETS:
        rows = es.read_ledger_rows("DE", m, limit=100000)          # all in-universe rows with a stored summary (read-only copy)
        universe[m] = rows
    with httpx.Client(headers={"User-Agent": "BIAP-Global/1.0 evidence-verification"}) as client:
        todo = [(m, r) for m in MARKETS for r in universe[m]
                if (r.get("company") or {}).get("isin") in reg and not (r["company"].get("filing_period_end"))]
        for i in range(0, len(todo), BATCH):
            mem, disk = guard()
            batch = todo[i:i + BATCH]
            for m, r in batch:
                co = r["company"]; e = reg[co["isin"]]; t = co["ticker"]
                ok = matches(co, e["fund"])
                if ok is False:
                    outcome[(m, t)] = "registry_period_differs_from_stored_figures"; continue
                if ok is None:
                    outcome[(m, t)] = "esef_registry_unverified_against_row"; continue
                st = probe(e["url"], client)
                if st in (200, 206):
                    overlay[(m, t)] = e["period_end"]; outcome[(m, t)] = "RESOLVED"
                else:
                    outcome[(m, t)] = f"official_source_unreachable:{st}"
            log.append({"batch": i // BATCH + 1, "size": len(batch), "memAvailMB": mem, "diskFreeMB": disk})
            time.sleep(1.0)

    # tally the full 904-company universe, split benchmark peers (top payload rows) vs other companies
    tally = {}
    for m in MARKETS:
        peers = {r["company"]["ticker"] for r in es.read_ledger_rows("DE", m)}          # the payload rows that feed the benchmark
        c = Counter()
        for r in universe[m]:
            co = r["company"]; t = co["ticker"]
            grp = "peer" if t in peers else "other"
            dated = bool(co.get("filing_period_end")) or (m, t) in overlay
            if dated:
                cat = "dated_exact" if co.get("filing_period_end") else "dated_via_registry_overlay"
            elif co.get("raw_provider_fields", {}).get("de_bf_period_granularity") == "year_only":
                cat = "undated_year_only_BF" + ("" if co.get("sector") else "+no_sector")
            else:
                cat = "undated_no_period_source" + ("" if co.get("sector") else "+no_sector")
            c[(grp, cat)] += 1
        tally[m] = {f"{g}|{k}": v for (g, k), v in sorted(c.items())}
        db = sqlite3.connect(DATA / f"analysis-ledger/DE__{m}.sqlite3")
        nosum = dict(db.execute("SELECT status, COUNT(*) FROM ledger WHERE in_universe=1 AND summary IS NULL GROUP BY status").fetchall()); db.close()
        tally[m]["_totals"] = {"ledger_in_universe": len(universe[m]) + sum(nosum.values()), "without_stored_analysis": nosum, "universe_with_analysis": len(universe[m]), "peers": len(peers), "overlay_resolved": sum(1 for k in overlay if k[0] == m)}

    # dry-run rebuilds: baseline vs with overlay (in memory only)
    def fixture(c, e, rows):
        d = NOW.date().isoformat()
        return ([{"ticker": x["company"]["ticker"], "price": x["company"].get("price") or 0, "quoteDate": d} for x in rows], [], "OFFLINE-FIXTURE")
    orig = es.read_ledger_rows
    results = {}
    for label, use in (("baseline", False), ("with_overlay", True)):
        def patched(country, exchange, *, limit=None, _use=use):
            rows = orig(country, exchange, limit=limit)
            if _use:
                for r in rows:
                    k = (exchange.upper(), r["company"]["ticker"])
                    if k in overlay:
                        r["company"]["filing_period_end"] = overlay[k]
            return rows
        es.read_ledger_rows = patched
        results[label] = {}
        for m in MARKETS:
            guard()
            o = es.rebuild_from_ledger("DE", m, quote_fetch=fixture, now=NOW, dry_run=True)
            fb = o.get("freshness") or o.get("benchmark") or {}
            results[label][m] = {k: o.get(k) for k in ("status", "replaced", "problems", "ledgerRows", "peerCount", "excludedPct", "undatedPct") if k in o}
            results[label][m]["raw"] = {k: (v if isinstance(v, (str, int, float, bool, type(None))) else str(v)[:300]) for k, v in o.items() if k not in ("rows",)}
        es.read_ledger_rows = orig

    OUT.write_text(json.dumps({"generatedAt": NOW.isoformat(), "batches": log, "outcomes": dict(Counter(outcome.values())),
                               "outcomeByTicker": {f"{m}:{t}": v for (m, t), v in outcome.items()},
                               "overlay": {f"{m}:{t}": v for (m, t), v in overlay.items()}, "tally": tally, "dryRun": results},
                              indent=1, default=str))
    print(json.dumps({"outcomes": dict(Counter(outcome.values())), "tally": tally,
                      "dryRun": {a: {m: {k: v for k, v in d.items() if k != "raw"} for m, d in b.items()} for a, b in results.items()}}, indent=1, default=str))


if __name__ == "__main__":
    main()
