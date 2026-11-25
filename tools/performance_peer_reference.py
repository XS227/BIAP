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
    by_sector, by_cell = {}, {}
    n_files = n_used = n_fin = n_nosector = 0
    h = hashlib.sha256()
    for f in sorted((data / "fundamentals").glob("*/*/*/latest.json")):
        n_files += 1
        d = json.loads(f.read_text(encoding="utf-8"))
        ident, fund = d.get("identity") or {}, d.get("fundamentals") or {}
        h.update(f"{ident.get('country')}/{ident.get('exchange')}/{ident.get('ticker')}/{d.get('filingPeriodEnd')}".encode())
        sec = (sectors.get(ident.get("isin") or "") or {}).get("sector")
        sec = {"industrial": "Industrials", "information technology": "Technology", "consumer cyclicals": "Consumer Discretionary"}.get((sec or "").casefold(), sec)
        kw = {k: v for k, v in fund.items() if k in fields and k not in ("country", "exchange", "ticker", "name", "currency")}
        c = GlobalCompany(country=ident.get("country") or "", exchange=ident.get("exchange") or "", currency=fund.get("reporting_currency") or "",
                          ticker=ident.get("ticker") or "", name=fund.get("name") or "", **kw)
        if sec:
            c.sector = sec
        if _is_financial(c) or (sectors.get(ident.get("isin") or "") or {}).get("kind") == "bank":
            n_fin += 1
            continue
        if not sec:
            n_nosector += 1
            continue
        vals = metric_values(c)
        if all(v is None for v in vals.values()):
            continue
        n_used += 1
        market = f"{ident.get('country')}:{ident.get('exchange')}"
        for key, store in ((sec, by_sector), (f"{sec}|{market}", by_cell)):
            slot = store.setdefault(key, {m: [] for m in METRICS})
            for m in METRICS:
                if vals[m] is not None:
                    slot[m].append(round(vals[m], 6))
    def pack(store):
        return {k: {"n": max(len(v[m]) for m in METRICS), **{m: sorted(v[m]) for m in METRICS}} for k, v in sorted(store.items())}
    body = {"schema": 1, "builtAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "metrics": list(METRICS),
            "source": {"fundamentalsFiles": n_files, "used": n_used, "financialsSkipped": n_fin, "noSectorSkipped": n_nosector,
                       "inventorySha256": h.hexdigest(), "note": "stored statements, one latest filing per issuer; sector from the official universe classification, else the ISIN sector reference"},
            "sector": pack(by_sector), "sectorMarket": pack(by_cell)}
    body["contentSha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    out.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {out}: {n_used} issuers used of {n_files} files, {len(by_sector)} sectors, {len(by_cell)} sector-market cells")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
