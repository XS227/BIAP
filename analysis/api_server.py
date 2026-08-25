"""
Minimal HTTP wrapper around the Kiasha decision layer.

Proposed as an ADDITIVE endpoint alongside the existing biap-mobile
contract (GET /stock/watchlist, TSETMC-only, unchanged). This exposes:

  GET /stock/recommendation/{code}

  {
    "code": "SAMPLE1",
    "call": "BUY" | "HOLD" | "SELL",
    "score": 0.45,
    "generatedAt": "2026-08-25T12:00:00Z",
    "breakdown": [ { agent, vote, confidence, trust_score, maturity,
                     weight_normalized, reasoning }, ... ]
  }

Currently backed by MOCK_COMPANIES only (see data_sample.py) — CODAL/TSETMC
ingestion is not wired in yet (see PROJECT_STATUS.md, "Open blockers").

Run locally:
    pip install -r requirements.txt
    uvicorn api_server:app --reload --port 8088
"""

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from data_sample import SAMPLE_COMPANY
from kiasha import decide

app = FastAPI(title="BIAP Kiasha recommendation service")

# Keyed by ticker. Only one mock entry until real CODAL/TSETMC ingestion
# replaces this with a live lookup.
MOCK_COMPANIES = {SAMPLE_COMPANY["ticker"]: SAMPLE_COMPANY}


@app.get("/health")
def health():
    return {"status": "ok", "mode": "mock", "companies": list(MOCK_COMPANIES)}


@app.get("/stock/recommendation/{code}")
def recommendation(code: str):
    company = MOCK_COMPANIES.get(code.upper())
    if company is None:
        raise HTTPException(status_code=404, detail=f"no data for {code}")

    decision = decide(company)
    return {
        "code": company["ticker"],
        "call": decision.call,
        "score": decision.weighted_score,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "breakdown": decision.breakdown,
    }
