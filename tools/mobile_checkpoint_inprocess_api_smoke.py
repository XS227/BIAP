#!/usr/bin/env python3
"""GET-only, in-process FastAPI tests against explicit read-only snapshot paths.

No server is started, no production HTTP endpoint is contacted, and no jobs,
market-data providers, AI proxies, or trading endpoints are invoked. Global
snapshots can be dated backups; this is NOT a live staging API certificate.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import global_routes  # noqa: E402
import iran_company_routes  # noqa: E402


MARKETS = [
    ("US", "NASDAQ"), ("GB", "LSE"), ("DE", "XETRA"),
    ("NO", "EURONEXT_OSLO"), ("SE", "NASDAQ_STOCKHOLM"),
    ("FR", "EURONEXT_PARIS"), ("IT", "EURONEXT_MILAN"),
    ("NL", "EURONEXT_AMSTERDAM"), ("FI", "NASDAQ_HELSINKI"),
    ("ES", "BME_MADRID"),
]


def readonly_connection(path: Path):
    return sqlite3.connect("file:" + quote(str(path.resolve()), safe="/") + "?mode=ro", uri=True)


def global_check(snapshot: Path):
    app = FastAPI()
    app.include_router(global_routes.router)
    client = TestClient(app)
    os.environ["BIAP_CHECKPOINT_SAVED_READONLY"] = "1"
    os.environ.pop("BIAP_CHECKPOINT_GLOBAL_AI", None)
    output = {}
    with tempfile.TemporaryDirectory(prefix="biap-inprocess-readonly-") as root:
        (Path(root) / "analysis-ledger").symlink_to(snapshot.resolve(), target_is_directory=True)
        os.environ["BIAP_GLOBAL_DATA_DIR"] = root
        for country, exchange in MARKETS:
            market = country + ":" + exchange
            file = snapshot / (country + "__" + exchange + ".sqlite3")
            sample = []
            if file.is_file():
                with readonly_connection(file) as db:
                    tickers = [r[0] for r in db.execute(
                        "SELECT ticker FROM ledger WHERE in_universe=1 AND result IS NOT NULL ORDER BY ticker LIMIT 300"
                    )]
                for ticker in tickers:
                    res = client.get("/global/checkpoint/saved-company",
                                     params={"country": country, "exchange": exchange, "ticker": ticker})
                    if res.status_code != 200:
                        continue
                    value = res.json()
                    if (value.get("mode") != "SAVED_READ_ONLY" or value.get("proxyCalled") is not False
                            or value.get("eligibleForInvestmentDecision") is not False):
                        continue
                    sample.append({"ticker": ticker, "http": res.status_code,
                                   "evidence": value.get("evidence", {}).get("status"),
                                   "audit": value.get("audit", {}).get("status"),
                                   "agents": len(value.get("agents", []))})
                    if len(sample) == 3:
                        break
            output[market] = {"threeRealSavedResponses": len(sample) == 3, "sample": sample}
    return output


def iran_check(listed: Path, performance: Path):
    os.environ["BIAP_LISTED_COMPANY_DB"] = str(listed)
    os.environ["BIAP_PERFORMANCE_DB"] = str(performance)
    os.environ["BIAP_CHECKPOINT_IRAN_READONLY"] = "1"
    os.environ.pop("BIAP_CHECKPOINT_IRAN_AI", None)
    app = FastAPI()
    app.include_router(iran_company_routes.router)
    app.dependency_overrides[iran_company_routes.require_user_id] = lambda: "checkpoint-readonly-test"
    client = TestClient(app)
    output = {}
    for symbol in ("پکرمان", "فولاد", "خودرو"):
        company = client.get("/iran/company/stored", params={"q": symbol})
        audit = client.get("/iran/company/audit", params={"q": symbol})
        ok = company.status_code == 200 and audit.status_code == 200
        result = {"companyHttp": company.status_code, "auditHttp": audit.status_code}
        if ok:
            c, a = company.json(), audit.json()
            result.update({"code": c.get("identity", {}).get("code"),
                           "agentCount": len(c.get("agents", [])),
                           "kiashaStored": c.get("kiasha") is not None,
                           "financialsAvailable": c.get("financials", {}).get("available"),
                           "priceStatus": c.get("price", {}).get("status"),
                           "auditChecks": len(a.get("checks", []))})
        result["ok"] = ok
        output[symbol] = result
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--global-snapshot-dir", type=Path, required=True)
    p.add_argument("--iran-listed-db", type=Path, required=True)
    p.add_argument("--iran-performance-db", type=Path, required=True)
    args = p.parse_args()
    for path in (args.global_snapshot_dir, args.iran_listed_db, args.iran_performance_db):
        if not path.exists():
            p.error("Missing explicit read-only snapshot path: " + str(path))
    global_results = global_check(args.global_snapshot_dir)
    iran_results = iran_check(args.iran_listed_db, args.iran_performance_db)
    all_ok = all(x["threeRealSavedResponses"] for x in global_results.values()) and all(
        x["ok"] for x in iran_results.values()
    )
    print(json.dumps({
        "mode": "IN_PROCESS_GET_ONLY", "source": "explicit saved snapshots, not a live staging deployment",
        "global": global_results, "iran": iran_results,
        "apiReadOnlySnapshotChecksComplete": all_ok,
        "aiProxyCalled": False, "marketDataFetched": False, "historyModified": False,
        "fullCheckpointReady": False,
    }, ensure_ascii=False, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
