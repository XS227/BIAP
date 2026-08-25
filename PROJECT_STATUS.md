# BIAP — Project Status (analysis/backend side)

_Last updated: 2026-08-25_

This repo is the analysis/decision layer for BIAP. It's separate from
[`-biap-mobile`](https://github.com/nasrindadashi-cloud/-biap-mobile), which
owns the Expo/React Native app and already talks to a live backend at
`https://biap.dadashi.no/api` (server `89.42.199.20`).

**Nothing here is deployed or wired into the live backend yet.** This is a
working local prototype, built and smoke-tested, ready to be integrated.

## What this is

An intelligent financial/business analysis pipeline for Iranian equities:

```
CODAL (disclosures/reports) ─┐
                              ├─> normalize/store ─> agent team ─> Kiasha ─> Buy/Hold/Sell
TSETMC (price/volume/P-E) ───┘
```

- **`analysis/agents.py`** — 4 analyst agents (fundamental, risk, forecast,
  comparison), each returns a vote (-1..+1), a confidence (0..1), and a
  short reasoning string from a normalized company record.
- **`analysis/kiasha.py`** — the decision layer. Reuses the trust/maturity
  design from the Kiasha capital allocator already running in the Arena
  trading project (`trust_score = accuracy × stability × n_factor`,
  maturity tiers `experiment/observed/production/core` with weight caps
  10/20/35/50%). Instead of reallocating trading capital across
  strategies, it reallocates *decision weight* across the agent team and
  blends the votes into a call + explanation.
- **`analysis/data_sample.py`** — mock CODAL + TSETMC data for one
  fictitious company. Real ingestion is not built (see blockers below).
- **`analysis/api_server.py`** — minimal FastAPI wrapper exposing:

  ```
  GET /stock/recommendation/{code}
  {
    "code": "SAMPLE1",
    "call": "BUY" | "HOLD" | "SELL",
    "score": 0.45,
    "generatedAt": "...",
    "breakdown": [ { agent, vote, confidence, trust_score, maturity,
                     weight_normalized, reasoning }, ... ]
  }
  ```

  Verified locally (`uvicorn api_server:app`): `/health`, a real
  `SAMPLE1` recommendation, and a 404 for an unknown code all work.

## How this is meant to plug into `-biap-mobile`

The mobile app's existing contract (`src/lib/api.ts`,
`GET /stock/watchlist`) returns TSETMC price data only
(`StockItem: name, code, lastPrice, closingPrice, yesterdayPrice, change,
changePercent`). It is **untouched by this repo**.

The proposal is additive: `GET /stock/recommendation/{code}` as a second
endpoint the stock detail screen (`src/app/stock/[code].tsx`) could call
alongside `fetchWatchlist()` to show a Kiasha call/explanation. No changes
needed to the existing watchlist contract or screens that don't want it.

## Open blockers (real, not yet solved)

1. **CODAL/TSETMC ingestion is unresolved.** Neither `codal.ir` nor
   `tsetmc.com` are reachable from the VPS this was built on (connection
   refused / timed out on both) — looks like outbound network restriction
   rather than a dead site. Needs to be researched/fetched from a vantage
   point that can actually reach them (e.g. from inside Iran, or via
   whatever the mobile app's own `89.42.199.20` backend already uses to
   get its live TSETMC prices — that backend clearly *can* reach TSETMC
   today, so its ingestion path is the fastest lead).
2. **No trading/order API confirmed.** This only ever produces a
   recommendation — it does not and should not place trades. Whether any
   Iranian broker exposes an API for that is a separate, unanswered
   question (raised, not resolved).
3. **`TRACK_RECORDS` in `kiasha.py` are hardcoded placeholders**, not real
   per-agent history. A live backend would need to log each
   recommendation + its eventual outcome and compute
   accuracy/stability/lifetime-calls from that, the same way Arena's
   Kiasha computes trust_score from real trade history.
4. **Stack/hosting unknown on my side** — I don't have access to
   `89.42.199.20`. This FastAPI service is a reference implementation of
   the contract, not necessarily what should run in production; feel free
   to reimplement the same `/stock/recommendation/{code}` shape in
   whatever stack the existing backend already uses.

## Running it locally

```bash
cd analysis
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api_server:app --reload --port 8088
curl localhost:8088/stock/recommendation/SAMPLE1
```

Or run the pipeline standalone without HTTP:

```bash
cd analysis && python3 main.py
```
