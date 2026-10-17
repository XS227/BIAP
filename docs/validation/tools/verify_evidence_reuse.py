"""Non-destructive verification of 9a6c755 on an ISOLATED copy of stored data. Quotes are an OFFLINE fixture (no network)."""
import zlib, copy, dataclasses, hashlib, json, os, sys, sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
S = Path("/tmp/claude-1000/-home-ubuntu/77ebaf4a-d9b5-47e7-bd1d-569cda9d9a26/scratchpad")
DATA = S / "h/data"
os.environ.update(BIAP_GLOBAL_DATA_DIR=str(DATA), BIAP_GLOBAL_ONLINE_FIRST="1")
sys.path.insert(0, str(S / "wt/analysis"))
from global_markets import evidence_store as es, freshness as fr, benchmark_refresh as br
from global_markets.source_cache import read_json
from global_markets.scan_service import _scan_cache_path
from global_markets.models import GlobalCompany, SourceEvidence
from global_markets import service as svc
from global_markets.core_agents import run_core_agents
from global_markets.advanced_agents import run_advanced_agents
from global_markets.agents import evidence_agent
from global_markets.distress import distress_agent
from global_markets.providers import ProviderDiagnostics
from global_markets.credit_scoring import score_legal_entity_company

MARKETS = [("DE","XETRA"),("DE","FRANKFURT"),("US","NASDAQ"),("US","NYSE"),("GB","LSE"),("FR","EURONEXT_PARIS"),
           ("IT","EURONEXT_MILAN"),("SE","NASDAQ_STOCKHOLM"),("NO","EURONEXT_OSLO")]
NOW = datetime.now(timezone.utc).replace(microsecond=0)
FIELDS = {f.name for f in dataclasses.fields(GlobalCompany)}
SE_FIELDS = {f.name for f in dataclasses.fields(SourceEvidence)}

def digest(root):
    h = hashlib.sha256(); n = 0
    for sub in ("fundamentals", "market", "shares", "filings"):
        for p in sorted((root / sub).rglob("*")):
            if p.is_file():
                h.update(f"{p.relative_to(root)}:{p.stat().st_size}:{int(p.stat().st_mtime)}".encode()); n += 1
    return h.hexdigest()[:16], n

def ledger_digest(cc, ex):
    p = Path(es.ledger_path(cc, ex)); c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        return hashlib.sha256(json.dumps(c.execute("SELECT ticker,status,analyzed_at,call,summary FROM ledger ORDER BY ticker").fetchall(), default=str).encode()).hexdigest()[:16]
    finally: c.close()

def fixture(skip=(), date_offset=0, mult=1.0):
    """Offline stand-in for the one online step (current exchange quotes): stored price x mult, dated today-offset."""
    d = (NOW - timedelta(days=date_offset)).date().isoformat()
    return lambda c, e, rows: ([{"ticker": r["company"]["ticker"], "price": (r["company"].get("price") or 0) * mult, "quoteDate": d}
                                for r in rows if r["company"]["ticker"] not in skip], [], "OFFLINE-FIXTURE")

def redecide(co_dict, now):
    kw = {k: v for k, v in co_dict.items() if k in FIELDS}
    kw["sources"] = [SourceEvidence(**{k: v for k, v in e.items() if k in SE_FIELDS}) if isinstance(e, dict) else e for e in (kw.get("sources") or [])]
    kw["material_event_flags"] = tuple(kw.get("material_event_flags") or ())
    kw["sector_pe"] = None            # as in a fresh analysis: the peer benchmark must be (re)derived from the cache, not carried over
    kw["raw_provider_fields"] = {k: v for k, v in (kw.get("raw_provider_fields") or {}).items()
                                 if not k.startswith(("peer_", "sector_pe", "exchange_pe", "price_state"))}
    co = GlobalCompany(**kw)
    enriched = svc._derive_metrics(co)
    signals = run_core_agents(enriched) + run_advanced_agents(enriched)
    evidence = evidence_agent(enriched, signals, now=now)
    distress = distress_agent(enriched)
    credit = score_legal_entity_company(enriched, distress)
    raw, dconf = svc._weighted_score(signals)
    score, conf = raw * evidence.confidence_multiplier, dconf * evidence.confidence_multiplier
    p = svc._analysis_payload(enriched, ProviderDiagnostics("ok", "ok"), signals, evidence, distress, credit, raw, score, dconf, conf)
    return p["call"], p["decisionIntegrity"]["preliminaryCall"], (p["governance"] or {}).get("action"), enriched

out = {"at": NOW.isoformat(), "commit": "9a6c755", "markets": []}
before_files = digest(DATA)
for cc, ex in MARKETS:
    r = {"country": cc, "exchange": ex}
    r["ledgerDigestBefore"] = ledger_digest(cc, ex)
    inv = es.inventory(cc, ex); r["inventory"] = inv
    rows = es.read_ledger_rows(cc, ex, limit=100000)
    allrows = rows
    # --- reusable evidence / missing critical inputs, from the FULL stored analysis (compressed `result` column)
    _c0 = sqlite3.connect(f"file:{es.ledger_path(cc, ex)}?mode=ro", uri=True)
    full = []
    for tk, st, evs, blob in _c0.execute("SELECT ticker,status,evidence_status,result FROM ledger WHERE in_universe=1 AND result IS NOT NULL"):
        try: full.append((tk, st, evs, json.loads(zlib.decompress(blob)).get("company") or {}))
        except Exception: pass
    _c0.close()
    def has(co, k): return co.get(k) not in (None, "", 0, 0.0)
    CRIT = ("price", "price_observed_at", "filing_period_end", "sector")
    def earn(co): return has(co, "eps") or has(co, "net_income")
    complete = [f for f in full if f[1] == "COMPLETE"]
    reusable = [f for f in complete if f[2] == "PASS" and all(has(f[3], k) for k in CRIT) and earn(f[3])]
    missing = {k: sum(1 for f in complete if not has(f[3], k)) for k in CRIT}
    missing["market_cap(informational)"] = sum(1 for f in complete if not has(f[3], "market_cap"))
    missing["earnings(eps|net_income)"] = sum(1 for f in complete if not earn(f[3]))
    r["evidence"] = {"storedResults": len(full), "complete": len(complete), "reusableValidated": len(reusable),
                     "completeButMissingCritical": len(complete) - len(reusable), "missingCriticalAmongComplete": missing}
    # --- legacy (24h rule) on the existing cache
    path = _scan_cache_path(cc, ex); legacy = read_json(path, default={}) or {}
    base = legacy.get("cachedAt")
    r["legacy"] = {"cachedAt": base, "rows": len((legacy.get("payload") or {}).get("deepResults") or [])}
    try:
        b = datetime.fromisoformat(str(base).replace("Z", "+00:00"))
        r["legacy"]["ageHoursNow"] = round((NOW - b).total_seconds() / 3600, 1)
        r["legacy"]["usableUnder24hRule"] = (NOW - b).total_seconds() / 3600 <= 24
    except Exception: r["legacy"]["usableUnder24hRule"] = False
    # --- reconstruction (dry-run first = no write; then real write to ISOLATED copy)
    dry = es.rebuild_from_ledger(cc, ex, quote_fetch=fixture(), now=NOW, dry_run=True)
    r["rebuildDry"] = {k: dry.get(k) for k in ("status", "ledgerRows", "rowsRepriced", "rowsExcluded", "coveragePct", "excludedReasons", "problems")}
    r["rebuildDry"]["fileUnchangedAfterDry"] = (read_json(path, default={}) or {}) == legacy
    real = es.rebuild_from_ledger(cc, ex, quote_fetch=fixture(), now=NOW)
    r["rebuild"] = {k: real.get(k) for k in ("status", "replaced", "ledgerRows", "rowsRepriced", "rowsExcluded", "coveragePct", "excludedReasons", "problems", "quotesAsOf")}
    new = read_json(path, default={}) or {}
    r["afterTTL"] = {}
    for lab, t in (("now", NOW), ("plus25h", NOW + timedelta(hours=25)), ("plus7d", NOW + timedelta(days=7))):
        v = fr.evaluate(new, cc, t)
        r["afterTTL"][lab] = {"usable": v["usable"], "reason": v.get("reason")}
    r["staleQuotes"] = {}
    # negative: stale quotes (10d old) must not be accepted as current; missing quotes -> exclusion
    stale = es.rebuild_from_ledger(cc, ex, quote_fetch=fixture(date_offset=10), now=NOW, dry_run=True)
    r["staleQuotes"] = {"status": stale.get("status"), "rowsRepriced": stale.get("rowsRepriced"), "problems": (stale.get("problems") or [])[:2]}
    # --- stale prices never presented as current; stored evidence not relabelled
    bytes0 = path.read_bytes()
    def partial(c, e, rows):
        q, errs, src = fixture()(c, e, rows)
        for i, qq in enumerate(q):
            if i % 10 == 3: qq["quoteDate"] = (NOW - timedelta(days=10)).date().isoformat()
        return q, errs, src
    pr = es.rebuild_from_ledger(cc, ex, quote_fetch=partial, now=NOW)
    pw = read_json(path, default={}) or {}
    prow = (pw.get("payload") or {}).get("deepResults") or []
    ex_rows = [x for x in prow if (x.get("company") or {}).get("benchmark_excluded_reason") == "quote_stale"]
    r["stalePartial"] = {"status": pr.get("status"), "excludedQuoteStale": len(ex_rows),
                         "excludedRowsKeepingMultiples": sum(1 for x in ex_rows if any(x["company"].get(k) is not None for k in ("pe", "pb", "ev_ebitda"))),
                         "excludedRowsMarkedCurrent": sum(1 for x in ex_rows if str(x["company"].get("price_observed_at") or "")[:10] == NOW.date().isoformat()),
                         "repricedRowsDatedAfterQuote": sum(1 for x in prow if (x["company"].get("benchmark_repriced_from") or {}).get("quoteDate") and
                                                           str(x["company"].get("price_observed_at"))[:10] != x["company"]["benchmark_repriced_from"]["quoteDate"])}
    path.write_bytes(bytes0)
    cur = [x for x in (new.get("payload") or {}).get("deepResults") or []]
    _c1 = sqlite3.connect(f"file:{es.ledger_path(cc, ex)}?mode=ro", uri=True)
    led_at = {t: a for t, a in _c1.execute("SELECT ticker, analyzed_at FROM ledger")}; _c1.close()
    r["preservation"] = {"rebuiltRows": len(cur), "inputsAsOfEqualsLedgerAnalyzedAt": sum(1 for x in cur if x.get("inputsAsOf") == led_at.get(x.get("ticker"))),
                         "benchmarkValidatedAt": (new.get("benchmark") or {}).get("validatedAt"), "baseCachedAt": new.get("cachedAt"),
                         "cachedAtRewrittenToNow": str(new.get("cachedAt") or "")[:16] == NOW.isoformat()[:16]}
    fund = DATA / "fundamentals" / cc / ex
    smp = sorted(fund.glob("*/latest.json"))[:25]; ok = 0; hist = 0
    for p in smp:
        try: json.loads(p.read_text()); ok += 1
        except Exception: pass
        hist += len(list((p.parent / "history").glob("*.json")))
    r["preservation"]["fundamentalsSampleReadable"] = f"{ok}/{len(smp)}"; r["preservation"]["historyFilesInSample"] = hist
    # --- decisions on BUY candidates, re-run offline through the real governance path
    buys = [x for x in allrows if x.get("call") == "BUY_CANDIDATE"]
    _c = sqlite3.connect(f"file:{es.ledger_path(cc, ex)}?mode=ro", uri=True)
    for x in buys:   # full stored analysis (compressed `result` column) so enrichment/provenance fields are kept
        blob = _c.execute("SELECT result FROM ledger WHERE ticker=?", (x["ticker"],)).fetchone()[0]
        x["company"] = json.loads(zlib.decompress(blob))["company"]
    _c.close()
    dec = {"ledgerBuyCandidates": len(buys), "reDecidedWithRebuiltBenchmark": {}, "withExpiredBenchmark": {}, "staleBuyBasePriceState": {},
           "missingCritical": {}, "errors": 0}
    def tally(d, k): d[k] = d.get(k, 0) + 1
    # expired legacy benchmark = original cache restored at cachedAt+25h is modelled by removing the benchmark (peer state unusable)
    new_bytes = path.read_text() if path.exists() else None
    # control: ORIGINAL (still <24h) legacy benchmark with the same offline re-decision, to separate harness gap from rebuild effect
    path.write_text(json.dumps(legacy)) if legacy else None
    ctrl = {}
    for x in buys:
        try: call, *_ = redecide(x["company"], NOW); tally(ctrl, call); x["_orig"] = call
        except Exception: pass
    dec["withOriginalLegacyBenchmark"] = ctrl
    path.write_text(new_bytes)
    for x in buys:
        try: x["_rebuilt"] = redecide(x["company"], NOW)[0]
        except Exception: pass
    dec["sameCallOriginalVsRebuilt"] = sum(1 for x in buys if x.get("_orig") == x.get("_rebuilt"))
    dec["buyOrig"] = sum(1 for x in buys if x.get("_orig") == "BUY_CANDIDATE"); dec["buyRebuilt"] = sum(1 for x in buys if x.get("_rebuilt") == "BUY_CANDIDATE")
    dec["buyBothOrigAndRebuilt"] = sum(1 for x in buys if x.get("_orig") == x.get("_rebuilt") == "BUY_CANDIDATE")
    dec["buyOnlyRebuilt"] = sum(1 for x in buys if x.get("_rebuilt") == "BUY_CANDIDATE" and x.get("_orig") != "BUY_CANDIDATE")
    for x in buys:
        co = x["company"]
        try:
            call, pre, act, enr = redecide(co, NOW); tally(dec["reDecidedWithRebuiltBenchmark"], call)
            ps = (enr.raw_provider_fields or {}).get("price_state", {}).get("state"); tally(dec["staleBuyBasePriceState"], f"stored price state={ps}")
            call2, *_ = redecide({**co, "price_observed_at": NOW.isoformat()}, NOW); tally(dec.setdefault("withCurrentTargetPrice", {}), call2)
        except Exception as e:
            dec["errors"] += 1; dec.setdefault("errorSamples", []).append(f"{type(e).__name__}: {str(e)[:100]}"); continue
    # expired: temporarily point to cache with cachedAt aged >24h and no v2 benchmark block
    exp = copy.deepcopy(new); exp.pop("benchmark", None); exp["cachedAt"] = (NOW - timedelta(hours=30)).isoformat()
    path.write_text(json.dumps(exp))
    for x in buys:
        try: call, *_ = redecide(x["company"], NOW); tally(dec["withExpiredBenchmark"], call)
        except Exception: pass
    # missing-critical mutations on the REBUILT benchmark
    path.write_text(new_bytes)
    old_day = (NOW - timedelta(days=40)).isoformat()
    muts = {"no_price": {"price": None, "market_cap": None, "price_observed_at": None},
            "no_earnings": {"eps": None, "pe": None, "net_income": None, "ebitda": None, "operating_cash_flow": None, "free_cash_flow": None, "ev_ebitda": None},
            "no_filing_period": {"filing_period_end": None, "filing_observed_at": None}, "no_sector": {"sector": None},
            "stale_price_40d": {"price_observed_at": old_day}}
    for name, m in muts.items():
        cnt = {}
        for x in buys:
            try: call, *_ = redecide({**x["company"], **m}, NOW); tally(cnt, call)
            except Exception as e: tally(cnt, "ERROR:" + type(e).__name__)
        dec["missingCritical"][name] = cnt
    r["decisions"] = dec
    r["ledgerDigestAfter"] = ledger_digest(cc, ex)
    r["ledgerUnchanged"] = r["ledgerDigestBefore"] == r["ledgerDigestAfter"]
    r["inventoryUnchanged"] = es.inventory(cc, ex) == inv
    print(cc, ex, r["rebuild"]["status"], r["rebuild"].get("rowsRepriced"), dec["reDecidedWithRebuiltBenchmark"], dec["withExpiredBenchmark"], flush=True)
    out["markets"].append(r)
out["evidenceFilesBefore"], out["evidenceFilesAfter"] = before_files, digest(DATA)
json.dump(out, open(S / "h/result.json", "w"), indent=1, default=str)
