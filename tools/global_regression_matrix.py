#!/usr/bin/env python3
"""Representative six-market regression matrix for BIAP Global (SE, NO, FR, IT, GB, US).

Runs real companies through the in-process API and checks structural invariants for each
archetype: profitable, loss-making, dual-class, financially distressed, bank. It is meant to
be run against a SANDBOX copy of the data directory, never production:

    BIAP_GLOBAL_DATA_DIR=/path/to/sandbox/data \
    BIAP_GLOBAL_MARKET_CACHE_HOURS=100000 BIAP_GLOBAL_FUNDAMENTALS_CACHE_HOURS=100000 \
    python tools/global_regression_matrix.py [--json out.json]

Exit status is non-zero if any invariant fails. Invariants are about consistency, not about
price-dependent values, so the matrix stays valid as markets move.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

# (country, exchange, currency, ticker, archetype)
MATRIX = [
    ("SE", "NASDAQ_STOCKHOLM", "SEK", "VOLCAR.B", "loss-making+NCI"),
    ("SE", "NASDAQ_STOCKHOLM", "SEK", "VOLV.B", "profitable+dual-class"),
    ("SE", "NASDAQ_STOCKHOLM", "SEK", "ERIC.B", "profitable+dual-class"),
    ("SE", "NASDAQ_STOCKHOLM", "SEK", "ATCO.A", "profitable+dual-class"),
    ("SE", "NASDAQ_STOCKHOLM", "SEK", "DUST", "loss-making"),
    ("SE", "NASDAQ_STOCKHOLM", "SEK", "ELUX.B", "distressed"),
    ("SE", "NASDAQ_STOCKHOLM", "SEK", "SEB.A", "bank+dual-class"),
    ("NO", "EURONEXT_OSLO", "NOK", "EQNR", "profitable+cross-currency"),
    ("NO", "EURONEXT_OSLO", "NOK", "NAS", "distressed"),
    ("NO", "EURONEXT_OSLO", "NOK", "ELK", "loss-making"),
    ("NO", "EURONEXT_OSLO", "NOK", "DNB", "bank"),
    ("FR", "EURONEXT_PARIS", "EUR", "TTE", "profitable+cross-currency"),
    ("FR", "EURONEXT_PARIS", "EUR", "RNO", "loss-making"),
    ("FR", "EURONEXT_PARIS", "EUR", "FRVIA", "distressed"),
    ("FR", "EURONEXT_PARIS", "EUR", "CS", "insurer"),
    ("IT", "EURONEXT_MILAN", "EUR", "ENI", "profitable"),
    ("IT", "EURONEXT_MILAN", "EUR", "STLAM", "loss-making"),
    ("IT", "EURONEXT_MILAN", "EUR", "TIT", "distressed"),
    ("IT", "EURONEXT_MILAN", "EUR", "ISP", "bank"),
    ("GB", "LSE", "GBP", "SHEL", "profitable+cross-currency"),
    ("GB", "LSE", "GBP", "AZN", "profitable+cross-currency"),
    ("GB", "LSE", "GBP", "BP.", "near-zero-owner-profit"),
    ("GB", "LSE", "GBP", "VOD", "loss-making"),
    ("GB", "LSE", "GBP", "SBRY", "distressed"),
    ("US", "NASDAQ", "USD", "AAPL", "profitable"),
    ("US", "NASDAQ", "USD", "GOOGL", "profitable+dual-class"),
    ("US", "NASDAQ", "USD", "GOOG", "profitable+dual-class"),
    ("US", "NASDAQ", "USD", "INTC", "loss-making"),
    ("US", "NASDAQ", "USD", "UAL", "distressed"),
    ("US", "NYSE", "USD", "BRK.B", "dual-class+insurer"),
    ("US", "NYSE", "USD", "F", "loss-making"),
    ("US", "NYSE", "USD", "JPM", "bank"),
]


def check(result: dict, archetype: str) -> list[str]:
    """Invariants that must hold for every analysed company."""
    failures: list[str] = []
    company = result.get("company") or {}
    distress = result.get("distress") or {}
    credit = result.get("creditScoring") or {}
    notes = " ".join(map(str, (company.get("raw_provider_fields") or {}).get("derived_metrics") or []))

    if result.get("call") not in {"BUY_CANDIDATE", "HOLD_OR_WATCH", "AVOID_OR_REVIEW", "NO_RECOMMENDATION"}:
        failures.append(f"unknown call {result.get('call')!r}")
    overall, decision, evidence = (result.get(k) for k in ("overallCalibratedConfidence", "decisionConfidence", "evidenceConfidence"))
    if None not in (overall, decision, evidence) and abs(overall - decision * evidence) > 1e-4:
        failures.append("overall confidence is not decision x evidence")
    if "confidenceBreakdown" not in result:
        failures.append("confidenceBreakdown missing")

    # Agent 9 / Agent 10 must never silently disagree.
    if distress.get("status") == "HIGH_RISK" and credit.get("investment_grade") and credit.get("indicated_rating_sp"):
        if (credit.get("rating_consistency") or {}).get("status") != "CONFLICT":
            failures.append("Agent 9 HIGH_RISK vs Agent 10 investment grade not flagged CONFLICT")
    if distress.get("status") == "HIGH_RISK" and not distress.get("severe_triggers"):
        failures.append("HIGH_RISK without recorded triggers")

    # EPS must agree in sign with the earnings measure it belongs to, or be withheld.
    eps = company.get("eps")
    meta = (company.get("raw_provider_fields") or {}).get("oam_credit_extraction") or (company.get("raw_provider_fields") or {}).get("esef_credit_extraction") or {}
    owners = meta.get("net_income_owners")
    earnings = owners if owners is not None else company.get("net_income")
    if eps not in (None, 0) and earnings not in (None, 0) and (eps > 0) != (earnings > 0):
        failures.append(f"EPS {eps} contradicts earnings {earnings} and was not withheld")

    # Valuation figures must be internally consistent where both sides exist.
    cap, price, shares = company.get("market_cap"), company.get("price"), company.get("shares_outstanding")
    if cap and price and shares and "ADR" not in notes and "per_share_basis_mismatch" not in notes:
        ratio = cap / (price * shares)
        if not 0.5 <= ratio <= 2.0 and "series" not in notes:
            failures.append(f"market_cap/(price*shares)={ratio:.2f}")
    pe = company.get("pe")
    if pe is not None and pe <= 0:
        failures.append(f"non-positive P/E {pe}")
    ev = company.get("ev_ebitda")
    if ev is not None and ev <= 0:
        failures.append(f"non-positive EV/EBITDA {ev}")
    if (company.get("reporting_currency") or company.get("currency")) != company.get("currency") and pe is not None:
        if "fx:" not in notes and "company_market_cap" not in notes:
            failures.append("cross-currency P/E without a recorded FX conversion")

    if "dual-class" in archetype and cap is not None and "nordic_series" in json.dumps(company.get("raw_provider_fields") or {}):
        series = (company["raw_provider_fields"].get("nordic_series") or {})
        if series.get("status") == "verified" and abs(series.get("market_cap", 0) - cap) > 1:
            failures.append("verified issuer market cap differs from the summed series")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", help="write full results here")
    parser.add_argument("--only", help="comma-separated tickers")
    args = parser.parse_args()
    from fastapi.testclient import TestClient

    import global_api_server

    client = TestClient(global_api_server.app)
    only = {t.strip().upper() for t in args.only.split(",")} if args.only else None
    report, failed = [], 0
    for country, exchange, currency, ticker, archetype in MATRIX:
        if only and ticker.upper() not in only:
            continue
        response = client.post("/global/analyze", json={"country": country, "exchange": exchange, "ticker": ticker, "currency": currency})
        if response.status_code != 200:
            report.append({"ticker": ticker, "archetype": archetype, "error": response.status_code, "failures": [f"HTTP {response.status_code}"]})
            failed += 1
            print(f"FAIL {country}:{ticker:9} {archetype:28} HTTP {response.status_code}")
            continue
        result = response.json()
        failures = check(result, archetype)
        company = result.get("company") or {}
        row = {
            "country": country, "ticker": ticker, "archetype": archetype, "call": result.get("call"),
            "market_cap": company.get("market_cap"), "pe": company.get("pe"), "ev_ebitda": company.get("ev_ebitda"),
            "agent9": (result.get("distress") or {}).get("status"),
            "agent10_rating": (result.get("creditScoring") or {}).get("indicated_rating_sp"),
            "rating_consistency": ((result.get("creditScoring") or {}).get("rating_consistency") or {}).get("status"),
            "failures": failures,
        }
        report.append(row)
        failed += bool(failures)
        print(f"{'FAIL' if failures else 'ok  '} {country}:{ticker:9} {archetype:28} cap={row['market_cap']} pe={row['pe']} A9={row['agent9']} A10={row['agent10_rating']} {row['rating_consistency']} {failures or ''}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1, default=str))
    print(f"\n{len(report) - failed}/{len(report)} cases pass")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
