#!/usr/bin/env python3
"""Read-only Checkpoint 1 API sampler. Never triggers scans, analyses or writes.

Examples:
  python tools/mobile_checkpoint_readonly_smoke.py --global-base-url https://HOST/global-api \
    --iran-base-url https://HOST/api \
    --market US:NASDAQ --market GB:LSE --iran-symbol پکرمان \
    --iran-symbol خودرو --iran-symbol خساپا

Global checks three distinct saved ledger rows per requested market (one GET).
Iran checks three explicit symbols via read-only symbol search (one GET each).
This does NOT validate the AI proxy, live price reconciliation or full analysis.
No credentials or raw financial payloads are printed.
"""
import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


def clean_symbol(value):
    return "".join(str(value or "").translate(str.maketrans({"ي": "ی", "ك": "ک"})).split()).casefold()


def sample_global(payload):
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {"ok": False, "reason": "missing_rows", "sample": []}
    seen, sample = set(), []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip()
        key = ticker.upper()
        if not key or key in seen:
            continue
        seen.add(key)
        ledger = row.get("ledger") if isinstance(row.get("ledger"), dict) else {}
        sample.append({
            "ticker": ticker,
            "status": ledger.get("status"),
            "sourcePresent": bool(ledger.get("source") or row.get("source")),
            "evidenceStatus": (row.get("evidence") or {}).get("status")
                if isinstance(row.get("evidence"), dict) else None,
        })
        if len(sample) == 3:
            break
    return {"ok": len(sample) == 3, "reason": None if len(sample) == 3 else "fewer_than_three_distinct_issuers", "sample": sample}


def match_iran(payload, requested):
    rows = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {"ok": False, "reason": "missing_items", "symbol": requested}
    key = clean_symbol(requested)
    for row in rows:
        if not isinstance(row, dict):
            continue
        if key in (clean_symbol(row.get("symbol")), clean_symbol(row.get("code"))):
            return {"ok": True, "symbol": requested, "codePresent": bool(row.get("code")),
                    "namePresent": bool(row.get("name")), "market": row.get("market")}
    return {"ok": False, "reason": "symbol_not_found", "symbol": requested}


def get_json(base, path):
    token = os.environ.get("BIAP_READONLY_API_TOKEN", "").strip()
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(base.rstrip("/") + path, headers=headers, method="GET")
    with urlopen(req, timeout=12) as response:
        return json.load(response)


def self_test():
    assert sample_global({"rows": [{"ticker": "A"}, {"ticker": "A"}, {"ticker": "B"}, {"ticker": "C"}]})["ok"]
    assert not sample_global({"rows": [{"ticker": "A"}]})["ok"]
    assert not sample_global({"rows": None})["ok"]
    assert match_iran({"items": [{"symbol": "پكرمان", "code": "12", "name": "Test"}]}, "پکرمان")["ok"]
    assert not match_iran({"items": [{"symbol": "خودرو"}]}, "پکرمان")["ok"]
    print("offline parser self-test: PASS")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--global-base-url", help="Approved Global API base, e.g. https://HOST/global-api")
    p.add_argument("--iran-base-url", help="Approved Iran API base, e.g. https://HOST/api")
    p.add_argument("--market", action="append", default=[], metavar="COUNTRY:EXCHANGE")
    p.add_argument("--iran-symbol", action="append", default=[])
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.global_base_url or not args.iran_base_url or not args.market or len(args.iran_symbol) != 3:
        p.error("Supply both API base URLs, at least one --market and exactly three --iran-symbol values")
    if not all(base.startswith("https://") for base in (args.global_base_url, args.iran_base_url)):
        p.error("HTTPS API bases are required")
    if len({clean_symbol(symbol) for symbol in args.iran_symbol}) != 3:
        p.error("Three distinct Iran symbols are required")
    results = {"mode": "READ_ONLY", "global": {}, "iran": {}, "apiCompanyChecksComplete": False}
    success = True
    for market in args.market:
        if ":" not in market:
            p.error("--market must be COUNTRY:EXCHANGE")
        country, exchange = (part.strip().upper() for part in market.split(":", 1))
        if not country or not exchange or not all(x.isalnum() or x in "_-" for x in country + exchange):
            p.error("invalid country or exchange")
        path = "/global/analysis-ledger?" + urlencode({"country": country, "exchange": exchange, "limit": 100})
        try:
            result = sample_global(get_json(args.global_base_url, path))
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            result = {"ok": False, "reason": type(exc).__name__}
        results["global"][market] = result
        success = success and result["ok"]
    for symbol in args.iran_symbol:
        path = "/stock/symbols?" + urlencode({"q": symbol, "limit": 30})
        try:
            result = match_iran(get_json(args.iran_base_url, path), symbol)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            result = {"ok": False, "reason": type(exc).__name__, "symbol": symbol}
        results["iran"][symbol] = result
        success = success and result["ok"]
    # This sampler cannot prove the proxy, price correctness or decision quality.
    results["apiCompanyChecksComplete"] = success
    results["fullCheckpointReady"] = False
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
