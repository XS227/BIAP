#!/usr/bin/env python3
"""Isolated loopback HTTPS checkpoint smoke against explicit saved database copies.

Not a deployed staging service, not a live proxy test, and not proof of fresh data.
Only GET endpoints are exposed; AI/trading/scan routes are blocked. No APK build.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from mobile_checkpoint_inprocess_api_smoke import MARKETS, readonly_connection

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"/health", "/global/checkpoint/saved-company",
           "/iran/company/stored", "/iran/company/audit"}


def serve() -> None:
    sys.path.insert(0, str(ROOT / "analysis"))
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    import uvicorn
    import global_routes
    import iran_company_routes

    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    app.include_router(global_routes.router)
    app.include_router(iran_company_routes.router)
    app.dependency_overrides[iran_company_routes.require_user_id] = lambda: "isolated-checkpoint"

    @app.middleware("http")
    async def deny_unsafe_requests(request, call_next):
        if request.method != "GET":
            return JSONResponse({"error": "GET_ONLY"}, status_code=405)
        if request.url.path not in ALLOWED:
            return JSONResponse({"error": "NOT_EXPOSED"}, status_code=404)
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"mode": "ISOLATED_HTTPS_SNAPSHOT", "liveProxyCalled": False}

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ["CHECKPOINT_HTTPS_PORT"]),
                ssl_certfile=os.environ["CHECKPOINT_TLS_CERT"],
                ssl_keyfile=os.environ["CHECKPOINT_TLS_KEY"], log_level="error")


def _check_copy(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_file() and not resolved.is_dir():
        raise ValueError("Missing snapshot: " + str(path))
    # Explicitly refuse active data directories; use backups or isolated copies.
    if str(resolved).startswith("/var/lib/biap-global/analysis-ledger"):
        raise ValueError("Active Global ledger forbidden; use a dated backup")
    if not (str(resolved).startswith("/tmp/") or "/backups/" in str(resolved)
            or "/backup-" in str(resolved)):
        raise ValueError("Only explicit /tmp or backup snapshots allowed: " + str(path))
    return resolved


def _get(base: str, path: str, params: dict, ctx: ssl.SSLContext) -> tuple[int, dict]:
    from urllib.request import urlopen
    url = base + path + ("?" + urlencode(params) if params else "")
    try:
        with urlopen(url, context=ctx, timeout=8) as response:
            return response.status, json.loads(response.read(2_000_000))
    except HTTPError as error:
        return error.code, {}


def check(args) -> dict:
    global_dir = _check_copy(args.global_snapshot_dir)
    listed = _check_copy(args.iran_listed_db)
    performance = _check_copy(args.iran_performance_db)
    if not global_dir.is_dir() or not listed.is_file() or not performance.is_file():
        raise ValueError("Expected a Global backup directory and two Iran database copies")
    with tempfile.TemporaryDirectory(prefix="biap-https-checkpoint-") as tmp:
        tmpdir = Path(tmp)
        (tmpdir / "analysis-ledger").symlink_to(global_dir, target_is_directory=True)
        cert, key = tmpdir / "cert.pem", tmpdir / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-days", "1", "-keyout", str(key), "-out", str(cert),
                        "-subj", "/CN=localhost",
                        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = os.environ.copy()
        env.update({"CHECKPOINT_HTTPS_PORT": str(port), "CHECKPOINT_TLS_CERT": str(cert),
                    "CHECKPOINT_TLS_KEY": str(key), "BIAP_GLOBAL_DATA_DIR": str(tmpdir),
                    "BIAP_LISTED_COMPANY_DB": str(listed),
                    "BIAP_PERFORMANCE_DB": str(performance),
                    "BIAP_CHECKPOINT_SAVED_READONLY": "1",
                    "BIAP_CHECKPOINT_IRAN_READONLY": "1",
                    "BIAP_CHECKPOINT_GLOBAL_AI": "0",
                    "BIAP_CHECKPOINT_IRAN_AI": "0",
                    "BIAP_AI_PROXY_URL": "", "BIAP_AI_PROXY_TOKEN": "",
                    "PYTHONDONTWRITEBYTECODE": "1"})
        base = f"https://localhost:{port}"
        ctx = ssl.create_default_context(cafile=str(cert))
        with (tmpdir / "server.log").open("wb") as logfile:
            proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve"],
                                    env=env, stdout=logfile, stderr=subprocess.STDOUT)
            try:
                for _ in range(60):
                    if proc.poll() is not None:
                        raise RuntimeError("HTTPS server exited during startup")
                    try:
                        code, health = _get(base, "/health", {}, ctx)
                        if code == 200 and health.get("liveProxyCalled") is False:
                            break
                    except (URLError, TimeoutError, ConnectionError):
                        pass
                    time.sleep(0.25)
                else:
                    raise RuntimeError("HTTPS loopback startup timeout")

                global_results = {}
                for country, exchange in MARKETS:
                    market = f"{country}:{exchange}"
                    db_file = global_dir / f"{country}__{exchange}.sqlite3"
                    sample = []
                    if db_file.is_file():
                        with readonly_connection(db_file) as db:
                            tickers = [row[0] for row in db.execute(
                                "SELECT ticker FROM ledger WHERE in_universe=1 AND result IS NOT NULL ORDER BY ticker LIMIT 300")]
                        for ticker in tickers:
                            status, data = _get(base, "/global/checkpoint/saved-company",
                                                {"country": country, "exchange": exchange,
                                                 "ticker": ticker}, ctx)
                            if (status == 200 and data.get("mode") == "SAVED_READ_ONLY"
                                    and data.get("proxyCalled") is False
                                    and data.get("eligibleForInvestmentDecision") is False):
                                sample.append({"ticker": ticker, "https": status,
                                               "agents": len(data.get("agents", [])),
                                               "kiashaPresent": bool((data.get("kiasha") or {}).get("call")),
                                               "financialQualityPresent": isinstance(data.get("financialQuality"), dict),
                                               "audit": data.get("audit", {}).get("status")})
                                if len(sample) == 3:
                                    break
                    global_results[market] = sample

                iran_results = {}
                for symbol in ("پکرمان", "فولاد", "خودرو"):
                    company_status, company = _get(base, "/iran/company/stored",
                                                   {"q": symbol}, ctx)
                    audit_status, audit = _get(base, "/iran/company/audit",
                                               {"q": symbol}, ctx)
                    iran_results[symbol] = {
                        "companyHttps": company_status, "auditHttps": audit_status,
                        "agents": len(company.get("agents", [])),
                        "kiashaPresent": bool((company.get("kiasha") or {}).get("call")),
                        "financialsAvailable": company.get("financials", {}).get("available"),
                        "auditFinancialsAvailable": audit.get("financialsAvailable"),
                        "auditChecks": len(audit.get("checks", [])),
                    }

                denied, _ = _get(base, "/global/scan", {}, ctx)
                from urllib.request import Request, urlopen
                try:
                    urlopen(Request(base + "/iran/company/ai-analysis", method="POST"),
                            context=ctx, timeout=8)
                    post_denied = False
                except HTTPError as error:
                    post_denied = error.code == 405
                ok = (all(len(v) == 3 and all(
                          row["agents"] >= 6 and row["kiashaPresent"]
                          and row["financialQualityPresent"]
                          and row["audit"] in ("UNVERIFIED", "INCOMPLETE", "INCONSISTENT")
                          for row in v) for v in global_results.values())
                      and all(v["companyHttps"] == 200 and v["auditHttps"] == 200
                              and v["agents"] == 7 and v["kiashaPresent"]
                              and v["auditChecks"] == 6
                              and type(v["financialsAvailable"]) is bool
                              and v["financialsAvailable"] == v["auditFinancialsAvailable"]
                              for v in iran_results.values())
                      and denied == 404 and post_denied)
                return {
                    "mode": "ISOLATED_LOOPBACK_HTTPS_WITH_TLS_VALIDATION",
                    "deployedStagingVerified": False, "liveAiProxyCalled": False,
                    "historyModified": False, "tradingRoutesBlocked": denied == 404,
                    "aiPostBlocked": post_denied, "global": global_results,
                    "iran": iran_results, "httpsSnapshotChecksComplete": ok,
                    "fullCheckpointReady": False,
                }
            except Exception as error:
                logfile.flush()
                detail = (tmpdir / "server.log").read_text(errors="replace")[-1000:]
                raise RuntimeError(f"{error}; server log: {detail}") from error
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--global-snapshot-dir", type=Path)
    parser.add_argument("--iran-listed-db", type=Path)
    parser.add_argument("--iran-performance-db", type=Path)
    options = parser.parse_args()
    if options.serve:
        serve()
    else:
        if not all((options.global_snapshot_dir, options.iran_listed_db,
                    options.iran_performance_db)):
            parser.error("All three snapshot paths are required")
        result = check(options)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["httpsSnapshotChecksComplete"] else 1)
