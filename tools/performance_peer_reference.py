#!/usr/bin/env python3
"""Build the versioned peer reference for the Performance Agent's sector-relative scoring (read-only on the data directory).

Usage: python tools/performance_peer_reference.py <global_data_dir> <out.json> [--sector-reference <entries.json>]
Reads <global_data_dir>/fundamentals/*/*/*/latest.json (stored statements only; no network), takes the sector from the ISIN-keyed sector
reference (<global_data_dir>/sector-reference/entries.json), skips financial institutions, computes the same metrics the agent uses
(performance_agent.metrics) and writes sorted value lists per sector and per sector x market. Refuses to overwrite an existing file.
The data directory is opened read-only; nothing is written there.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "analysis"))

from global_markets import performance_agent as pa          # noqa: E402
from global_markets.distress import _is_financial            # noqa: E402
from global_markets.models import GlobalCompany              # noqa: E402

METRICS = ("roa", "roe", "operating_margin", "cfo_to_net_income", "accrual_ratio")


def metric_values(c: GlobalCompany) -> dict:
    m = pa.metrics(c)
    return {"roa": m["roa"], "roe": m["roe"], "operating_margin": m["margins"]["operating"],
            "cfo_to_net_income": m["cash_quality"]["cfo_to_net_income"], "accrual_ratio": m["cash_quality"]["accrual_ratio"]}


def main(argv):
    args = argv[1:]
    sector_path = None
    if "--sector-reference" in args:
        i = args.index("--sector-reference")
        sector_path = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) != 2:
        print(__doc__)
        return 2
    data, out = Path(args[0]), Path(args[1])
    if out.exists():
        print(f"refusing to overwrite {out}")
        return 1
    sector_path = sector_path or data / "sector-reference" / "entries.json"
    sectors = json.loads(sector_path.read_text(encoding="utf-8"))["entries"]
    # official universe classification wins over the ISIN reference (same precedence as the request path: apply_sector_reference fills only empty sectors)
    for uf in sorted((data / "universe").glob("*/*.json")):
        rows = json.loads(uf.read_text(encoding="utf-8"))
        rows = rows.get("rows") or rows.get("instruments") or [] if isinstance(rows, dict) else rows
        for r in rows:
            if r.get("isin") and r.get("sector"):
                sectors[r["isin"]] = {**sectors.get(r["isin"], {}), "sector": r["sector"], "industry": r.get("industry"),
                                      "kind": (sectors.get(r["isin"]) or {}).get("kind")}
    fields = set(GlobalCompany.model_fields) if hasattr(GlobalCompany, "model_fields") else set(GlobalCompany.__dataclass_fields__)
    cfg = pa.load_config()
    R = cfg["relative"]
    supp = pa.load_sector_supplement(cfg).get("entries") or {}
    issuers = []                                   # (sector or None, market, values)
    n_files = n_fin = n_nosector = n_supp = 0
    h = hashlib.sha256()
    for f in sorted((data / "fundamentals").glob("*/*/*/latest.json")):
        n_files += 1
        d = json.loads(f.read_text(encoding="utf-8"))
        ident, fund = d.get("identity") or {}, d.get("fundamentals") or {}
        h.update(f"{ident.get('country')}/{ident.get('exchange')}/{ident.get('ticker')}/{d.get('filingPeriodEnd')}".encode())
        market = f"{ident.get('country')}:{ident.get('exchange')}"
        ref = sectors.get(ident.get("isin") or "") or {}
        sec = ref.get("sector")
        if not sec:
            sp = supp.get(f"{market}:{ident.get('ticker')}")
            if sp:
                sec, n_supp = sp["sector"], n_supp + 1
        sec = {"industrial": "Industrials", "information technology": "Technology", "consumer cyclicals": "Consumer Discretionary"}.get((sec or "").casefold(), sec)
        kw = {k: v for k, v in fund.items() if k in fields and k not in ("country", "exchange", "ticker", "name", "currency")}
        c = GlobalCompany(country=ident.get("country") or "", exchange=ident.get("exchange") or "", currency=fund.get("reporting_currency") or "",
                          ticker=ident.get("ticker") or "", name=fund.get("name") or "", **kw)
        if sec:
            c.sector = sec
        if _is_financial(c) or ref.get("kind") == "bank" or (sec or "").casefold() in ("financials", "financial services"):
            n_fin += 1
            continue
        vals = metric_values(c)
        if all(v is None for v in vals.values()):
            continue
        if not sec:
            n_nosector += 1
        issuers.append((sec, market, vals))
    scopes = {"sector": lambda sec, mk: sec, "sectorMarket": lambda sec, mk: f"{sec}|{mk}" if sec else None, "market": lambda sec, mk: mk}
    stores = {k: {} for k in scopes}
    for sec, mk, vals in issuers:                  # pass 1: metric arrays per scope
        for scope, keyf in scopes.items():
            key = keyf(sec, mk)
            if key is None:
                continue
            slot = stores[scope].setdefault(key, {"issuers": [], **{m: [] for m in METRICS}})
            slot["issuers"].append(vals)
            for m in METRICS:
                if vals[m] is not None:
                    slot[m].append(vals[m])
    for scope, store in stores.items():            # pass 2: every issuer's composite inside each scope it belongs to
        min_n = int(R["min_peers_sector"]) if scope == "sector" else int(R["min_peers_market"])
        for key, slot in store.items():
            for m in METRICS:
                slot[m].sort()
            comps = []
            for vals in slot["issuers"]:
                comp, _ = pa.scope_composite(vals, slot, min_n, int(R["min_metrics"]))
                if comp is not None:
                    comps.append(round(comp, 6))
            slot["composite"] = sorted(comps)
            slot["n"] = len(slot["issuers"])
            del slot["issuers"]
    n_used = len(issuers)
    def pack(store):
        return {k: {"n": v["n"], **{m: [round(x, 6) for x in v[m]] for m in (*METRICS, "composite")}} for k, v in sorted(store.items())}
    by_sector, by_cell = stores["sector"], stores["sectorMarket"]
    body = {"schema": 1, "builtAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "metrics": list(METRICS),
            "source": {"fundamentalsFiles": n_files, "used": n_used, "financialsSkipped": n_fin, "noSectorKeptForMarketWide": n_nosector, "sectorFromSupplement": n_supp,
                       "inventorySha256": h.hexdigest(), "note": "stored statements, one latest filing per issuer; sector from the official universe classification, else the ISIN sector reference, else the 'current sector, not point-in-time' supplement; issuers without any sector count only in the market-wide scope"},
            "sector": pack(by_sector), "sectorMarket": pack(by_cell), "market": pack(stores["market"])}
    body["contentSha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    out.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {out}: {n_used} issuers used of {n_files} files, {len(by_sector)} sectors, {len(by_cell)} sector-market cells")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
