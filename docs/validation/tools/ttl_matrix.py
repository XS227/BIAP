"""Per-country before/after benchmark-TTL matrix on an ISOLATED data copy. usage: ttl_matrix.py WORKDIR OUT.json [CC:EXCH ...]

WORKDIR is created; every data directory except scan-cache is symlinked from the isolated copy (read-only use), scan-cache
is copied. Nothing under /var/lib/biap-global is read or written. Per market it records:
  stored    - evidence inventory before and after (must be identical: nothing deleted or rewritten)
  legacy    - what the old single 24 h rule says at cachedAt+25 h (benchmark unavailable)
  rebuilt   - ledger_rebuild: rows kept / excluded, coverage, status (needs only current quotes online)
  after_ttl - freshness.evaluate on the rebuilt benchmark at now and at now+25 h with NO refresh (must stay usable)
  buy       - BUY candidates in the ledger vs. those that survive the quote + filing gate (decision_freshness)
"""
import hashlib, json, os, shutil, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SRC = "/home/ubuntu/biap-validation-20261016/data-u9"
R = "/home/ubuntu/biap-global/BIAP/analysis"
work, outp = Path(sys.argv[1]), sys.argv[2]
work.mkdir(parents=True, exist_ok=True)
for d in Path(SRC).iterdir():
    t = work / d.name
    if d.name == "scan-cache":
        if not t.exists():
            shutil.copytree(d, t)
    elif not t.exists():
        t.symlink_to(d)
os.environ.update(BIAP_GLOBAL_DATA_DIR=str(work), BIAP_GLOBAL_ONLINE_FIRST="1")
sys.path.insert(0, R)
from global_markets import evidence_store as es, freshness as fr          # noqa: E402
from global_markets.source_cache import read_json                          # noqa: E402
from global_markets.scan_service import _scan_cache_path                   # noqa: E402


def digest(root: Path) -> str:
    """Cheap fingerprint of stored evidence: names+sizes of fundamentals/market files and ledger db sizes."""
    h = hashlib.sha256()
    for sub in ("fundamentals", "market", "analysis-ledger"):
        for p in sorted((Path(SRC) / sub).rglob("*")):
            if p.is_file() and not p.name.endswith(("-shm", "-wal", ".lock")):
                h.update(f"{p.relative_to(SRC)}:{p.stat().st_size}".encode())
    return h.hexdigest()[:16]


markets = [tuple(a.upper().split(":", 1)) for a in sys.argv[3:]] or sorted(
    (p.parent.name, p.stem.split("__")[-1]) for p in [])  # replaced below
if not markets:
    for p in sorted((work / "scan-cache").glob("*/*.json")):
        markets.append((p.parent.name, p.stem))
before_digest = digest(work)
now = datetime.now(timezone.utc)
res = []
for cc, ex in markets:
    row = {"country": cc, "exchange": ex}
    try:
        row["stored"] = {"before": es.inventory(cc, ex)}
        wrap = read_json(_scan_cache_path(cc, ex), default={}) or {}
        base = datetime.fromisoformat(str(wrap.get("cachedAt")).replace("Z", "+00:00")) if wrap.get("cachedAt") else None
        legacy_expired = bool(base) and (base + timedelta(hours=25) - base).total_seconds() / 3600 > 24
        row["legacy"] = {"baseCachedAt": wrap.get("cachedAt"), "peerBenchmarkAt_plus25h": "UNAVAILABLE (24h rule)" if legacy_expired else "n/a",
                         "peerRowsLostAtExpiry": len((wrap.get("payload") or {}).get("deepResults") or [])}
        out = es.rebuild_from_ledger(cc, ex, now=now)
        row["rebuilt"] = {k: out.get(k) for k in ("status", "replaced", "ledgerRows", "rowsRepriced", "coveragePct", "problems", "quoteSource")}
        new = read_json(_scan_cache_path(cc, ex), default={}) or {}
        dims = {}
        for label, t in (("now", now), ("plus25h", now + timedelta(hours=25)), ("plus7d", now + timedelta(days=7))):
            v = fr.evaluate(new, cc, t)
            dims[label] = {"usable": v["usable"], "filing": v["dimensions"]["filing"]["state"], "quote": v["dimensions"]["quote"]["state"],
                           "reason": v.get("reason")}
        row["after_ttl"] = dims
        rows = (new.get("payload") or {}).get("deepResults") or []
        buys = [r for r in rows if (r.get("recommendation") or r.get("call")) in ("BUY", "BUY_CANDIDATE")
                or ((r.get("ledger") or {}).get("call") == "BUY_CANDIDATE")]
        ok = 0
        for r in buys:
            co = r.get("company") or {}
            q = fr.quote_state(co.get("price_observed_at"), now)
            f = fr.classify_filing(co.get("filing_period_end"), co.get("filing_period_end"))
            if fr.decision_freshness(quote=q, benchmark_usable=dims["now"]["usable"], filing=f)["buyAllowed"]:
                ok += 1
        row["buy"] = {"ledgerBuyCandidates": len(buys), "passCriticalGate": ok}
        row["stored"]["after"] = es.inventory(cc, ex)
        row["stored"]["unchanged"] = row["stored"]["before"] == row["stored"]["after"]
    except Exception as e:  # one market must not stop the matrix
        row["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    print(cc, ex, row.get("rebuilt", {}).get("status"), row.get("after_ttl", {}).get("plus25h", {}).get("usable"), row.get("error", ""), flush=True)
    res.append(row)
final = {"at": now.isoformat(), "evidenceDigestBefore": before_digest, "evidenceDigestAfter": digest(work), "markets": res}
final["evidenceUnchanged"] = final["evidenceDigestBefore"] == final["evidenceDigestAfter"]
json.dump(final, open(outp, "w"), indent=1, default=str)
