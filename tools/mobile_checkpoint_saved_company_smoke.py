#!/usr/bin/env python3
"""Opt-in, GET-only smoke check for stored Global company details on an ISOLATED staging API.

The route /global/checkpoint/saved-company must be explicitly enabled on staging.
Never use the production host, trigger /global/analyze, or treat results as trade-ready.
Example:
  python tools/mobile_checkpoint_saved_company_smoke.py \
    --base-url https://STAGING-HOST/global-api \
    --company US:NASDAQ:AAPL --company US:NASDAQ:MSFT --company US:NASDAQ:NVDA

This checks the actual three *stored* company responses, unlike the ledger-directory
sampler. It does NOT call biap-ai-proxy, validate Iran/CODAL, or prove market accuracy.
Output contains only validation metadata; raw financials and agent reasons are omitted.
"""
import argparse
import json
import math
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


def is_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_saved_company(value, country, exchange, ticker):
    """Fail closed on absent financials, agent votes, Kiasha or provenance."""
    if not isinstance(value, dict):
        return {"ok": False, "reason": "invalid_payload"}
    identity_ok = (
        value.get("ticker", "").upper() == ticker.upper()
        and value.get("country", "").upper() == country.upper()
        and value.get("exchange", "").upper() == exchange.upper()
    ) if all(isinstance(value.get(k), str) for k in ("ticker", "country", "exchange")) else False
    provenance_ok = (
        value.get("mode") == "SAVED_READ_ONLY"
        and value.get("proxyCalled") is False
        and value.get("eligibleForInvestmentDecision") is False
    )
    ledger = value.get("ledger") if isinstance(value.get("ledger"), dict) else {}
    evidence = value.get("evidence") if isinstance(value.get("evidence"), dict) else {}
    source_ok = all(isinstance(ledger.get(k), str) and ledger[k].strip()
                    for k in ("source", "analyzedAt")) and evidence.get("status") in ("PASS", "WARN", "BLOCK")
    financials = value.get("financials") if isinstance(value.get("financials"), dict) else {}
    required = ("revenue", "net_income", "total_assets", "total_liabilities", "total_equity")
    financials_ok = all(k in financials and (financials[k] is None or is_number(financials[k]))
                        for k in required) and any(is_number(financials[k]) for k in required)
    quality = value.get("financialQuality") if isinstance(value.get("financialQuality"), dict) else {}
    quality_ok = isinstance(quality.get("coreComplete"), bool) and (
        quality.get("coveragePct") is None or is_number(quality["coveragePct"])
    )
    audit = value.get("audit") if isinstance(value.get("audit"), dict) else {}
    audit_ok = (
        audit.get("method") == "DETERMINISTIC_STORED_CONSISTENCY"
        and audit.get("status") in ("UNVERIFIED", "INCOMPLETE", "INCONSISTENT")
        and audit.get("eligibleForInvestmentDecision") is False
        and audit.get("externallyVerified") is False
        and isinstance(audit.get("checks"), list) and len(audit["checks"]) >= 3
        and all(isinstance(c, dict) and (c.get("passed") is None or type(c.get("passed")) is bool)
                for c in audit["checks"])
    )
    agents = value.get("agents") if isinstance(value.get("agents"), list) else []
    names = [a.get("name") for a in agents if isinstance(a, dict) and isinstance(a.get("name"), str)]
    agents_ok = len(set(names)) >= 6 and all(
        is_number(a.get("vote")) and is_number(a.get("confidence"))
        for a in agents if isinstance(a, dict) and a.get("name") in names
    )
    kiasha = value.get("kiasha") if isinstance(value.get("kiasha"), dict) else {}
    kiasha_ok = isinstance(kiasha.get("call"), str) and bool(kiasha["call"].strip()) and is_number(kiasha.get("confidence"))
    checks = {
        "identity": identity_ok, "savedReadOnly": provenance_ok, "sourceAndEvidence": bool(source_ok),
        "financialFields": financials_ok, "financialQuality": quality_ok,
        "deterministicAudit": audit_ok, "sixAgentVotes": agents_ok, "kiasha": kiasha_ok,
    }
    return {"ok": all(checks.values()), "checks": checks, "agentCount": len(set(names)),
            "evidenceStatus": evidence.get("status") if isinstance(evidence.get("status"), str) else None,
            "auditStatus": audit.get("status") if isinstance(audit.get("status"), str) else None}


def self_test():
    good = {
        "mode": "SAVED_READ_ONLY", "proxyCalled": False, "eligibleForInvestmentDecision": False,
        "ticker": "ABC", "country": "US", "exchange": "NASDAQ",
        "ledger": {"source": "SAVED_LEDGER", "analyzedAt": "2026-10-30T12:00:00Z"},
        "evidence": {"status": "WARN"},
        "financials": {"revenue": 100, "net_income": -1, "total_assets": 200,
                       "total_liabilities": 70, "total_equity": 130},
        "financialQuality": {"coreComplete": True, "coveragePct": 80},
        "audit": {"method": "DETERMINISTIC_STORED_CONSISTENCY", "status": "UNVERIFIED",
                  "eligibleForInvestmentDecision": False, "externallyVerified": False,
                  "checks": [{"key": "identity", "passed": True}, {"key": "source", "passed": None},
                             {"key": "balance", "passed": True}]},
        "agents": [{"name": "Agent" + str(i), "vote": 0, "confidence": 0.6} for i in range(6)],
        "kiasha": {"call": "HOLD", "confidence": 0.5},
    }
    assert validate_saved_company(good, "US", "NASDAQ", "ABC")["ok"]
    for key, bad in (
        ("proxyCalled", True), ("eligibleForInvestmentDecision", True),
        ("financials", {}), ("agents", good["agents"][:5]),
        ("kiasha", {}), ("audit", {}), ("ledger", {}),
        ("audit", {**good["audit"], "checks": [{"key": "balance", "passed": 1}]}),
        ("audit", {**good["audit"], "checks": [{"key": "balance", "passed": 0}]}),
    ):
        candidate = {**good, key: bad}
        assert not validate_saved_company(candidate, "US", "NASDAQ", "ABC")["ok"], key
    assert not validate_saved_company(good, "US", "NASDAQ", "OTHER")["ok"]
    print("stored-company contract self-test: PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Isolated staging Global API base (HTTPS only)")
    parser.add_argument("--company", action="append", default=[], metavar="COUNTRY:EXCHANGE:TICKER")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.base_url or not args.company:
        parser.error("Provide staging --base-url and three --company entries per market")
    url = urlsplit(args.base_url)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.hostname in ("biap.dadashi.no", "setai.no", "www.setai.no")):
        parser.error("Only an explicitly designated isolated HTTPS staging host is allowed")
    groups = {}
    for raw in args.company:
        parts = raw.split(":", 2)
        if len(parts) != 3 or not all(p.strip() for p in parts):
            parser.error("Each --company must be COUNTRY:EXCHANGE:TICKER")
        country, exchange, ticker = (p.strip().upper() for p in parts)
        if not (country.isalpha() and len(country) == 2 and len(exchange) <= 64
                and all(c.isalnum() or c in "_-" for c in exchange) and len(ticker) <= 64):
            parser.error("Invalid country/exchange/ticker")
        groups.setdefault((country, exchange), []).append(ticker)
    if any(len(tickers) != 3 or len(set(tickers)) != 3 for tickers in groups.values()):
        parser.error("Exactly three distinct companies per market are required")
    results = {}
    complete = True
    for (country, exchange), tickers in groups.items():
        market = country + ":" + exchange
        results[market] = {}
        for ticker in tickers:
            query = urlencode({"country": country, "exchange": exchange, "ticker": ticker})
            req = Request(args.base_url.rstrip("/") + "/global/checkpoint/saved-company?" + query,
                          headers={"Accept": "application/json"}, method="GET")
            try:
                with urlopen(req, timeout=12) as response:
                    result = validate_saved_company(json.load(response), country, exchange, ticker)
            except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
                result = {"ok": False, "reason": type(exc).__name__}
            results[market][ticker] = result
            complete = complete and result["ok"]
    print(json.dumps({"mode": "STAGING_SAVED_READ_ONLY", "globalSavedCompanyChecksComplete": complete,
                      "iranCompanyChecksComplete": False, "proxyChecked": False,
                      "fullCheckpointReady": False, "markets": results}, ensure_ascii=False, indent=2))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
