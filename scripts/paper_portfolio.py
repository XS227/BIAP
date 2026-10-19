#!/usr/bin/env python3
"""Paper portfolio (no trading): freeze today's BIAP baskets, later measure 1/3/6-month returns.

Basket A = every stock BIAP currently calls BUY (BUY_CANDIDATE), per country.
Basket B = the Top-N most traded stocks per country (ledger quote.liquidityValue; see the
           audit workbook for what that value means per country - GB is market cap).
Benchmark = one index per country. Purpose: test whether BIAP avoiding popular stocks pays.

    snapshot   read-only on the ledgers; writes snapshots/<stamp>.json (+ .sha256). No network.
    add-investment  new snapshot with baskets D (investment BUY) + E (investment SELL); base file untouched
    returns    network (Yahoo chart API, public): equal-weight basket return per horizon vs benchmark.

Entry reference: the first close on/after the decision date from the SAME price source used for the
exit (consistent adjusted closes). The ledger price is stored for audit and compared as a sanity check.
Missing prices are excluded and counted - never treated as 0%.

Usage:
    python3 scripts/paper_portfolio.py research-snapshot   # 10 paper countries, baskets A-E, frozen research snapshot only
    python3 scripts/paper_portfolio.py snapshot --out-dir ~/biap_audit_2026-10-19/paper_portfolio
    python3 scripts/paper_portfolio.py returns  --snapshot <file>.json [--as-of 2026-11-19] [--prices-json test.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_decision_rule as A  # noqa: E402  (shared read-only ledger loader)

BENCHMARKS = {"US": "^GSPC", "GB": "^FTSE", "IT": "FTSEMIB.MI", "NO": "OSEBX.OL", "SE": "^OMX", "DE": "^GDAXI", "FR": "^FCHI",
              "NL": "^AEX", "FI": "^OMXH25", "ES": "^IBEX"}
BENCHMARK_NAMES = {"US": "S&P 500", "GB": "FTSE 100", "IT": "FTSE MIB", "NO": "Oslo Bors Benchmark", "SE": "OMXS30", "DE": "DAX", "FR": "CAC 40",
                   "NL": "AEX", "FI": "OMX Helsinki 25", "ES": "IBEX 35"}
SUFFIX = {"GB": ".L", "IT": ".MI", "NO": ".OL", "SE": ".ST", "DE": ".DE", "FR": ".PA", "US": "", "NL": ".AS", "FI": ".HE", "ES": ".MC"}
RESEARCH_COUNTRIES = ("US", "GB", "IT", "NO", "SE", "DE", "FR", "NL", "FI", "ES")   # the 10 paper countries (INVESTMENT_MODE_MARKETS)
HORIZONS = {"1m": 1, "3m": 3, "6m": 6}


def yahoo_symbol(country: str, ticker: str) -> str:
    t = ticker.upper()
    if country in ("SE", "US", "GB", "NO", "NL", "FI", "ES") and "." in t:
        t = t.replace(".", "-")   # ATCO.A -> ATCO-A.ST, BRK.B -> BRK-B
    return t + SUFFIX[country]


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


# ---------------------------------------------------------------- snapshot
def snapshot(args) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="biap-pp-", dir=args.tmp_dir))
    try:
        data = A.load_all(Path(args.ledger_dir), tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    now = datetime.now(timezone.utc)
    snap = {"schema": 1, "decision_timestamp_utc": now.isoformat(timespec="seconds"), "decision_date": now.date().isoformat(),
            "top_n": args.top_n, "engine": "ledger as stored; rule per audit_decision_rule.py (commit 0f149a2 era)",
            "benchmarks": {cc: {"symbol": s, "name": BENCHMARK_NAMES[cc]} for cc, s in BENCHMARKS.items()},
            "liquidity_basis": A.LIQUIDITY_BASIS, "countries": {}}
    for cc, rows in data.items():
        def member(r):
            return {"ticker": r.ticker, "yahoo_symbol": yahoo_symbol(cc, r.ticker), "exchange": r.exchange, "name": r.name,
                    "call": r.stored_call, "score": r.score, "confidence": r.confidence, "liquidity_value": r.liquidity_value,
                    "liquidity_rank": r.rank, "entry_price_ledger": r.price, "entry_price_date_ledger": r.quote_date,
                    "currency": r.currency, "ledger_analyzed_at": r.analyzed_at, "isin": r.isin}
        a = [member(r) for r in rows if r.stored_call == "BUY_CANDIDATE"]
        b = [member(r) for r in A.top_n(rows, args.top_n)]
        snap["countries"][cc] = {"basket_A_buy": a, "basket_B_top_traded": b,
                                 "overlap_AB": sorted({m["ticker"] for m in a} & {m["ticker"] for m in b})}
    out = Path(args.out_dir).expanduser() / "snapshots"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"snapshot_{now:%Y%m%dT%H%M%SZ}.json"
    blob = json.dumps(snap, indent=1, ensure_ascii=False, default=str)
    path.write_text(blob)
    digest = hashlib.sha256(blob.encode()).hexdigest()
    (path.with_suffix(".sha256")).write_text(f"{digest}  {path.name}\n")
    n = {cc: (len(v["basket_A_buy"]), len(v["basket_B_top_traded"])) for cc, v in snap["countries"].items()}
    print(f"snapshot {path} sha256 {digest[:16]}...  (A,B) per country: {n}")
    return 0


# ---------------------------------------------------------------- prices
class YahooPrices:
    def __init__(self):
        self.cache: dict[str, dict[str, float]] = {}

    def series(self, symbol: str, start: date, end: date) -> dict[str, float]:
        if symbol in self.cache:
            return self.cache[symbol]
        import urllib.parse
        import urllib.request
        p1 = int(datetime.combine(start - timedelta(days=7), datetime.min.time(), timezone.utc).timestamp())
        p2 = int(datetime.combine(end + timedelta(days=7), datetime.min.time(), timezone.utc).timestamp())
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
               f"?period1={p1}&period2={p2}&interval=1d&events=div%7Csplit")
        out: dict[str, float] = {}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 biap-paper-portfolio"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                res = json.load(resp)["chart"]["result"][0]
            closes = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or res["indicators"]["quote"][0]["close"]
            for ts, c in zip(res["timestamp"], closes):
                if c is not None:
                    out[datetime.fromtimestamp(ts, timezone.utc).date().isoformat()] = float(c)
        except Exception as exc:  # network/unknown symbol -> missing, reported
            print(f"  price fetch failed {symbol}: {exc}", file=sys.stderr)
        self.cache[symbol] = out
        return out


class JsonPrices:
    """{symbol: {YYYY-MM-DD: close}} - for tests and offline replays."""
    def __init__(self, path):
        self.data = json.loads(Path(path).read_text())

    def series(self, symbol, start, end):
        return self.data.get(symbol, {})


def close_on_or_after(series: dict[str, float], d: date, max_gap_days: int = 7):
    for i in range(max_gap_days + 1):
        k = (d + timedelta(days=i)).isoformat()
        if k in series:
            return k, series[k]
    return None, None


def basket_return(prices, members, entry: date, exit_: date):
    rets, missing = [], []
    for m in members:
        s = prices.series(m["yahoo_symbol"], entry, exit_)
        _, p0 = close_on_or_after(s, entry)
        # exit: last close on/before target date
        p1 = None
        for i in range(8):
            k = (exit_ - timedelta(days=i)).isoformat()
            if k in s:
                p1 = s[k]
                break
        if p0 and p1 and p0 > 0:
            rets.append((m["ticker"], p1 / p0 - 1.0))
        else:
            missing.append(m["ticker"])
    return rets, missing


def returns(args) -> int:
    snap = json.loads(Path(args.snapshot).read_text())
    entry = date.fromisoformat(snap["decision_date"])
    as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now(timezone.utc).date()
    prices = JsonPrices(args.prices_json) if args.prices_json else YahooPrices()
    rows = []
    for cc, v in snap["countries"].items():
        bsym = snap["benchmarks"][cc]["symbol"]
        for hname, months in HORIZONS.items():
            target = add_months(entry, months)
            if target > as_of:
                rows.append({"country": cc, "horizon": hname, "target_date": target.isoformat(), "status": "pending"})
                continue
            bs = prices.series(bsym, entry, target)
            _, b0 = close_on_or_after(bs, entry)
            b1 = next((bs[(target - timedelta(days=i)).isoformat()] for i in range(8) if (target - timedelta(days=i)).isoformat() in bs), None)
            bret = (b1 / b0 - 1.0) if b0 and b1 else None
            row = {"country": cc, "horizon": hname, "target_date": target.isoformat(), "status": "done",
                   "benchmark": bsym, "benchmark_return": bret}
            for key, label in (("basket_A_buy", "A"), ("basket_B_top_traded", "B"), ("basket_B_pr52_survivors", "S"), ("basket_D_investment_buy", "D"), ("basket_E_investment_sell", "E")):
                if key not in v:
                    continue
                rets, missing = basket_return(prices, v[key], entry, target)
                vals = [r for _, r in rets]
                row[f"{label}_n"] = len(vals)
                row[f"{label}_missing"] = len(missing)
                row[f"{label}_return"] = statistics.fmean(vals) if vals else None
                row[f"{label}_median"] = statistics.median(vals) if vals else None
                row[f"{label}_excess"] = (statistics.fmean(vals) - bret) if vals and bret is not None else None
                row[f"{label}_hit_rate_vs_bm"] = (sum(r > bret for r in vals) / len(vals)) if vals and bret is not None else None
            if "D_return" in row:
                row["D_minus_B"] = (row["D_return"] - row["B_return"]) if row["D_return"] is not None and row["B_return"] is not None else None
                row["D_minus_A"] = (row["D_return"] - row["A_return"]) if row["D_return"] is not None and row["A_return"] is not None else None
            if "E_return" in row and row.get("D_return") is not None and row["E_return"] is not None:
                row["D_minus_E"] = row["D_return"] - row["E_return"]     # >0 = investment ranking separates winners from losers
            if "S_return" in row:
                row["S_minus_B"] = (row["S_return"] - row["B_return"]) if row["S_return"] is not None and row["B_return"] is not None else None
            row["A_minus_B"] = (row["A_return"] - row["B_return"]) if row["A_return"] is not None and row["B_return"] is not None else None
            rows.append(row)
    out = Path(args.out) if args.out else Path(args.snapshot).with_name(Path(args.snapshot).stem + f"_returns_{as_of}.json")
    out.write_text(json.dumps({"snapshot": str(args.snapshot), "as_of": as_of.isoformat(), "rows": rows}, indent=1))
    pct = lambda x: "   n/a " if x is None else f"{x * 100:+7.2f}%"
    print(f"as of {as_of}; entry {entry} (equal-weight, adjusted closes; A=BUY basket, B=Top-{snap['top_n']} traded)")
    for r in rows:
        if r.get("S_n") is not None:
            print(f"  S (PR52 survivors) {r['country']} {r['horizon']}: {pct(r['S_return'])} ({r['S_n']}/{r['S_missing']}) vs bm {pct(r['S_excess'])}")
        if r.get("D_n") is not None:
            print(f"  D (investment BUY) {r['country']} {r['horizon']}: {pct(r['D_return'])} ({r['D_n']}/{r['D_missing']}) vs bm {pct(r['D_excess'])}  D-A {pct(r.get('D_minus_A'))}  D-Top50 {pct(r.get('D_minus_B'))}")
        if r.get("E_n") is not None:
            print(f"  E (investment SELL) {r['country']} {r['horizon']}: {pct(r['E_return'])} ({r['E_n']}/{r['E_missing']}) vs bm {pct(r['E_excess'])}  D-E {pct(r.get('D_minus_E'))}  (E should UNDERperform)")
    print("cty hz   benchmark        A(n/miss)        B(n/miss)     A-bm     B-bm    A-B")
    for r in rows:
        if r["status"] == "pending":
            print(f"{r['country']}  {r['horizon']}  pending until {r['target_date']}")
            continue
        print(f"{r['country']}  {r['horizon']}  {pct(r['benchmark_return'])}  {pct(r['A_return'])}({r['A_n']}/{r['A_missing']})  "
              f"{pct(r['B_return'])}({r['B_n']}/{r['B_missing']})  {pct(r['A_excess'])} {pct(r['B_excess'])} {pct(r['A_minus_B'])}")
    print(f"wrote {out}")
    return 0


def add_investment(args) -> int:
    """New snapshot = base snapshot + baskets D (investment BUY) and E (investment SELL) from the replay dump.

    The base file is never modified. One row per issuer (ISIN) - Xetra/Frankfurt and NASDAQ/NYSE duplicates collapse.
    Only the countries that have a benchmark here are kept (US GB IT NO SE DE FR).
    """
    base = json.loads(Path(args.base).read_text())
    dump = json.loads(Path(args.baskets).read_text())
    for cc, v in base["countries"].items():
        v.pop("basket_D_investment_buy", None)
        for key, side in (("basket_D_investment_buy", "BUY"), ("basket_E_investment_sell", "SELL")):
            seen, out = set(), []
            for m in sorted(dump.get(cc, {}).get(side, []), key=lambda m: -m["score"] if side == "BUY" else m["score"]):
                ident = m.get("isin") or (m["exchange"], m["ticker"])
                if ident in seen:
                    continue
                seen.add(ident)
                m = dict(m, yahoo_symbol=yahoo_symbol(cc, m["ticker"]), liquidity_rank=None)
                out.append(m)
            v[key] = out
    base["basket_labels"].update({"D": "basket_D_investment_buy (DECISION_MODE=investment BUY, all-market replay, one row per issuer)",
                                  "E": "basket_E_investment_sell (DECISION_MODE=investment SELL, expected to UNDERperform)"})
    base["amended_from"] = Path(args.base).name
    base["amendment_DE"] = ("D replaced and E added from tools/investment_mode_replay.py on stored ledgers "
                            "(feature/investment-mode); earlier D (investment_mode_compare.py) superseded; base file untouched")
    now = datetime.now(timezone.utc)
    base["investment_timestamp_utc"] = now.isoformat(timespec="seconds")
    path = Path(args.base).with_name(Path(args.base).stem.replace("_ABCD", "") + "_ABCDE.json")
    blob = json.dumps(base, indent=1, ensure_ascii=False, default=str)
    path.write_text(blob)
    digest = hashlib.sha256(blob.encode()).hexdigest()
    path.with_suffix(".sha256").write_text(f"{digest}  {path.name}\n")
    print(f"wrote {path} sha256 {digest[:16]}...")
    print({cc: (len(v["basket_D_investment_buy"]), len(v["basket_E_investment_sell"])) for cc, v in base["countries"].items()})
    return 0


def research_snapshot(args) -> int:
    """NEW snapshot for the research paper: 10 countries, baskets A-E, built ONLY from the frozen ledger snapshot.

    A = old (stored conservative) BUYs; B(pr52) = the A stocks that also pass the PR #52 BUY rules; C = Top-N most traded
    (key basket_B_top_traded); D / E = investment-mode BUY / SELL under the 2026-10-19 rules. One row per issuer (ISIN).
    No file of an earlier snapshot is touched.
    """
    import research_common as C
    rows, decisions, counted = C.load(Path(args.research_snapshot), args.tmp_dir)
    manifest = json.loads((Path(args.research_snapshot).expanduser() / "MANIFEST.sha256.json").read_text())
    ranks = {}
    by_cc: dict = {cc: [] for cc in RESEARCH_COUNTRIES}
    for r in rows:
        if r.analysed and r.key in counted and r.country in by_cc:
            by_cc[r.country].append(r)
    for cc, rs in by_cc.items():
        for i, r in enumerate(sorted((r for r in rs if r.liquidity > 0), key=lambda r: -r.liquidity), 1):
            ranks[r.key] = i

    def member(r, **extra):
        m = {"ticker": r.ticker, "yahoo_symbol": yahoo_symbol(r.country, r.ticker), "exchange": r.exchange.split(":", 1)[1],
             "name": r.name, "call": r.stored_call, "score": r.gate.score, "confidence": r.gate.confidence,
             "liquidity_value": r.liquidity, "liquidity_rank": ranks.get(r.key), "entry_price_ledger": r.price,
             "entry_price_date_ledger": r.quote_date, "currency": r.currency, "ledger_analyzed_at": r.analyzed_at, "isin": r.isin}
        m.update(extra)
        return m

    def one_per_issuer(members):
        seen, out = set(), []
        for m in members:
            ident = m.get("isin") or (m["exchange"], m["ticker"])
            if ident not in seen:
                seen.add(ident)
                out.append(m)
        return out

    now = datetime.now(timezone.utc)
    snap = {"schema": 1, "decision_timestamp_utc": now.isoformat(timespec="seconds"), "decision_date": "2026-10-19", "top_n": args.top_n,
            "engine": "frozen research snapshot 2026-10-19 (sha256 manifest verified); investment mode = feature/investment-mode rules of 2026-10-19",
            "research_snapshot_frozen_at": manifest["frozen_at"],
            "research_snapshot_manifest_sha256": hashlib.sha256((Path(args.research_snapshot).expanduser() / "MANIFEST.sha256.json").read_bytes()).hexdigest(),
            "benchmarks": {cc: {"symbol": BENCHMARKS[cc], "name": BENCHMARK_NAMES[cc]} for cc in RESEARCH_COUNTRIES},
            "liquidity_basis": {"GB": "MARKET CAPITALISATION, not traded value (lse_official.py:312)",
                                "*": "ledger quote.liquidityValue: turnover, else price x volume (adapter-specific; US price x volume)"},
            "basket_labels": {"A": "basket_A_buy (all stored conservative BUYs, old rule)",
                              "B": "basket_B_pr52_survivors (A that also pass the PR #52 BUY rules)",
                              "C": "basket_B_top_traded (Top-N most traded)",
                              "D": "basket_D_investment_buy (investment-mode BUY, 2026-10-19 rules, one row per issuer)",
                              "E": "basket_E_investment_sell (investment-mode SELL, expected to UNDERperform)"},
            "countries": {}}
    for cc in RESEARCH_COUNTRIES:
        rs = by_cc[cc]
        a_rows = [r for r in rs if r.stored_call == "BUY_CANDIDATE"]
        a = one_per_issuer(member(r) for r in sorted(a_rows, key=lambda r: -(r.gate.score or 0)))
        b = one_per_issuer(member(r) for r in sorted(a_rows, key=lambda r: -(r.gate.score or 0))
                           if C.A.decide(r.gate, C.GATE_PARAMS) == "BUY_CANDIDATE")
        top = one_per_issuer(member(r) for r in sorted((r for r in rs if r.liquidity > 0), key=lambda r: -r.liquidity))[:args.top_n]

        def inv(side):
            picks = [r for r in rs if decisions[r.key].call == side]
            picks.sort(key=lambda r: -decisions[r.key].score if side == "BUY" else decisions[r.key].score)
            return one_per_issuer(member(r, call=f"{side} (investment mode)", score=decisions[r.key].score,
                                         confidence=decisions[r.key].confidence, position_size_hint=decisions[r.key].position_size_hint,
                                         flags=list(decisions[r.key].flags), peer_scope=decisions[r.key].peer_scope,
                                         reason=decisions[r.key].reason, conservative_call=r.stored_call) for r in picks)
        snap["countries"][cc] = {"basket_A_buy": a, "basket_B_top_traded": top,
                                 "overlap_AB": sorted({m["ticker"] for m in a} & {m["ticker"] for m in top}),
                                 "basket_B_pr52_survivors": b, "basket_D_investment_buy": inv("BUY"), "basket_E_investment_sell": inv("SELL")}
    out = Path(args.out_dir).expanduser() / "snapshots"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"snapshot_20261019T055239Z_r3_research10_ABCDE.json"
    if path.exists():
        raise SystemExit(f"{path} exists - snapshots are never overwritten")
    blob = json.dumps(snap, indent=1, ensure_ascii=False, default=str)
    path.write_text(blob)
    digest = hashlib.sha256(blob.encode()).hexdigest()
    path.with_suffix(".sha256").write_text(f"{digest}  {path.name}\n")
    print(f"wrote {path} sha256 {digest[:16]}...")
    print("A, B(pr52), C(top), D, E per country:")
    for cc, v in snap["countries"].items():
        print(cc, len(v["basket_A_buy"]), len(v["basket_B_pr52_survivors"]), len(v["basket_B_top_traded"]),
              len(v["basket_D_investment_buy"]), len(v["basket_E_investment_sell"]))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--out-dir", default="~/biap_audit_2026-10-19/paper_portfolio")
    s.add_argument("--ledger-dir", default=A.DEFAULT_LEDGER_DIR)
    s.add_argument("--top-n", type=int, default=50)
    s.add_argument("--tmp-dir", default=None)
    r = sub.add_parser("returns")
    r.add_argument("--snapshot", required=True)
    r.add_argument("--as-of", default=None, help="YYYY-MM-DD (default today)")
    r.add_argument("--prices-json", default=None, help="offline prices {symbol:{date:close}} instead of Yahoo")
    r.add_argument("--out", default=None)
    ai = sub.add_parser("add-investment")
    ai.add_argument("--base", required=True, help="existing snapshot json (left untouched)")
    ai.add_argument("--baskets", required=True, help="baskets.json written by investment_mode_replay.py --dump-baskets")
    rs = sub.add_parser("research-snapshot", help="10-country A-E snapshot from the frozen research snapshot")
    rs.add_argument("--research-snapshot", default=str(Path("~/biap_research/snapshot_2026-10-19").expanduser()))
    rs.add_argument("--out-dir", default="~/biap_audit_2026-10-19/paper_portfolio")
    rs.add_argument("--tmp-dir", default=str(Path("~/biap_research/tmp").expanduser()))
    rs.add_argument("--top-n", type=int, default=50)
    args = ap.parse_args(argv)
    if args.cmd == "research-snapshot":
        return research_snapshot(args)
    if args.cmd == "add-investment":
        return add_investment(args)
    return snapshot(args) if args.cmd == "snapshot" else returns(args)


if __name__ == "__main__":
    raise SystemExit(main())
