"""Price-only refresh for already-enriched listed companies, with provenance and append-only history.

Why: the daily enrichment job (backlog mode) only touches never-enriched or new-filing companies, so the price
snapshot embedded in ``company_json["market"]`` of an enriched company stays frozen while ``updated_at`` keeps moving
(universe sync). This tool refreshes ONLY the price fields of that snapshot from the live TSETMC quote, never touches
CODAL fields, and records the replaced snapshot plus the new one in ``price_history`` first (nothing is overwritten
without a trace). Default is a dry run.

  python price_sync.py --codes 23214828924506640 [--apply]
  python price_sync.py --stale-days 3 --limit 50 [--apply]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from listed_company_store import ListedCompanyStore, _now_iso

PRICE_FIELDS = ("price", "last_price", "closing_price", "yesterday_price", "change", "change_percent")


def _market_age_days(company: dict, enriched_at: Optional[str]) -> Optional[float]:
    m = company.get("market") or {}
    fetched = m.get("quote_fetched_at")
    if isinstance(fetched, (int, float)) and fetched > 0:
        when = datetime.fromtimestamp(fetched, timezone.utc)
    elif enriched_at:
        try:
            when = datetime.fromisoformat(enriched_at.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return (datetime.now(timezone.utc) - when).total_seconds() / 86400


def stale_codes(store: ListedCompanyStore, stale_days: float, limit: int) -> list[str]:
    out: list[tuple[float, str]] = []
    with store._connect() as conn:
        for row in conn.execute("SELECT code, company_json, enriched_at FROM listed_companies WHERE company_json IS NOT NULL"):
            try:
                company = json.loads(row["company_json"]) or {}
            except ValueError:
                continue
            if (company.get("market") or {}).get("price") is None:
                continue
            age = _market_age_days(company, row["enriched_at"])
            if age is not None and age > stale_days:
                out.append((-(company["market"].get("trade_value_today") or 0.0), row["code"]))
    out.sort()
    return [code for _, code in out[:limit]]


def refresh_one(store: ListedCompanyStore, code: str, *, apply: bool,
                fetch: Optional[Callable[[str], Any]] = None) -> dict:
    if fetch is None:
        from market_data import find_quote
        fetch = lambda c: find_quote(c, use_cache=False)  # noqa: E731
    with store._connect() as conn:
        row = conn.execute("SELECT code, symbol, company_json, enriched_at FROM listed_companies WHERE code=?", (code,)).fetchone()
    if row is None or not row["company_json"]:
        return {"code": code, "status": "SKIPPED", "reason": "no enriched record (price-only refresh never creates one)"}
    company = json.loads(row["company_json"])
    market = dict(company.get("market") or {})
    try:
        quote = fetch(code)
    except Exception as exc:  # upstream failure is reported, never papered over
        return {"code": code, "symbol": row["symbol"], "status": "FAILED", "reason": f"{type(exc).__name__}: {str(exc)[:160]}"}
    if quote is None or getattr(quote, "last_price", None) is None and getattr(quote, "closing_price", None) is None:
        return {"code": code, "symbol": row["symbol"], "status": "FAILED", "reason": "no live quote returned"}
    price = quote.last_price if quote.last_price is not None else quote.closing_price
    observed = datetime.fromtimestamp(quote.fetched_at, timezone.utc).isoformat()
    old = {k: market.get(k) for k in ("price", "quote_fetched_at", "price_source", "valuation_source")}
    result = {"code": code, "symbol": row["symbol"], "status": "DRY_RUN" if not apply else "UPDATED",
              "previous": old, "new": {"price": price, "observedAt": observed, "source": quote.source}}
    if not apply:
        return result
    new_market = dict(market)
    new_market.update({"price": price, "last_price": quote.last_price, "closing_price": quote.closing_price,
                       "yesterday_price": quote.yesterday_price, "change": quote.change, "change_percent": quote.change_percent,
                       "price_source": quote.source, "quote_fetched_at": quote.fetched_at, "price_observed_at": observed,
                       "price_refreshed_by": "price_sync", "price_refreshed_at": _now_iso()})
    company["market"] = new_market
    with store._connect() as conn:
        store.append_price(conn, code, market, origin="preserved-before-price-sync", fallback_observed_at=row["enriched_at"])
        store.append_price(conn, code, new_market, origin="price-sync")
        # enriched_at and every non-price field stay as they were: this is not a full enrichment.
        conn.execute("UPDATE listed_companies SET company_json=? WHERE code=?", (json.dumps(company, ensure_ascii=False, sort_keys=True), code))
    return result


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--codes", help="comma-separated TSETMC instrument codes")
    ap.add_argument("--stale-days", type=float, default=3.0)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    args = ap.parse_args(argv)
    store = ListedCompanyStore()
    codes = [c.strip() for c in args.codes.split(",") if c.strip()] if args.codes else stale_codes(store, args.stale_days, args.limit)
    results = [refresh_one(store, c, apply=args.apply) for c in codes]
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return 0 if all(r["status"] in ("UPDATED", "DRY_RUN", "SKIPPED") for r in results) else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
