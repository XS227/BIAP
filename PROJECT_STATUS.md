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
- **`analysis/api_server.py`** — minimal FastAPI wrapper exposing recommendation
  plus the first guarded execution endpoints.
- **`analysis/execution.py`** — execution-policy boundary. Separates analysis
  from order handling and explicitly prevents live/AUTO trading.

## Implemented API prototype

### Recommendation

```
GET /stock/recommendation/{code}
{
  "code": "SAMPLE1",
  "call": "BUY" | "HOLD" | "SELL",
  "score": 0.45,
  "generatedAt": "...",
  "breakdown": [
    { agent, vote, confidence, trust_score, maturity,
      weight_normalized, reasoning }
  ]
}
```

### Execution scaffold — first build started 2026-08-25

The execution architecture from Discussion #1 has now moved from design into
code, but remains deliberately non-live.

```
Recommendation
     ↓
Execution Policy
     ↓
Paper / Approval
     ↓
Future Broker Adapter
     ↓
Future Broker API
```

Implemented now:

- `POST /orders/preview`
  - accepts stock code, BUY/SELL, quantity, optional limit price and mode;
  - recalculates the current Kiasha recommendation;
  - rejects contradictory BUY-vs-SELL requests;
  - creates an auditable order intent;
  - `paper` produces a simulation intent;
  - `approval` produces `PENDING_APPROVAL`;
  - `auto` is explicitly blocked.
- `POST /orders/submit`
  - accepts an existing prototype intent;
  - `paper` returns a simulated `PAPER_FILLED` receipt;
  - `approval` stays `PENDING_APPROVAL`;
  - never sends anything to a broker.
- `/health` now advertises execution capabilities:
  - paper: enabled
  - approval: enabled
  - auto: disabled
  - brokerConnected: false

Important: prototype order intents are currently stored **in memory only**.
Production requires authentication, persistent audit storage, account ownership,
idempotency, risk limits and a real broker adapter before any external order
submission can ever be enabled.

## How this is meant to plug into `-biap-mobile`

The mobile app's existing contract (`src/lib/api.ts`,
`GET /stock/watchlist`) returns TSETMC price data only
(`StockItem: name, code, lastPrice, closingPrice, yesterdayPrice, change,
changePercent`). It is **untouched by this repo**.

The proposal is additive: `GET /stock/recommendation/{code}` as a second
endpoint the stock detail screen (`src/app/stock/[code].tsx`) could call
alongside `fetchWatchlist()` to show a Kiasha call/explanation. No changes
needed to the existing watchlist contract or screens that don't want it.

The future mobile execution UX should also remain additive:

1. Show FIN recommendation.
2. User opens an order preview.
3. BIAP calls `/orders/preview`.
4. In paper mode, simulate only.
5. In approval mode, require explicit user approval before any future broker
   adapter is allowed to proceed.
6. AUTO remains disabled until separately approved and production-hardened.

## Open blockers (real, not yet solved)

1. **CODAL/TSETMC ingestion is unresolved.** Neither `codal.ir` nor
   `tsetmc.com` are reachable from the VPS this was built on (connection
   refused / timed out on both) — looks like outbound network restriction
   rather than a dead site. Needs to be researched/fetched from a vantage
   point that can actually reach them (e.g. from inside Iran, or via
   whatever the mobile app's own `89.42.199.20` backend already uses to
   get its live TSETMC prices — that backend clearly *can* reach TSETMC
   today, so its ingestion path is the fastest lead).
2. **No trading/order API confirmed.** Broker research in Discussion #1 is
   still preliminary. No Iranian broker API access is confirmed, and no
   credentials or broker connection exist in this repo.
3. **`TRACK_RECORDS` in `kiasha.py` are hardcoded placeholders**, not real
   per-agent history. A live backend would need to log each
   recommendation + its eventual outcome and compute
   accuracy/stability/lifetime-calls from that, the same way Arena's
   Kiasha computes trust_score from real trade history.
4. **Stack/hosting unknown on my side** — this FastAPI service is a reference
   implementation of the contract, not necessarily what should run in
   production. The existing BIAP backend at `89.42.199.20` still needs to be
   located/connected for live integration.
5. **Execution hardening not built yet.** Before any real broker integration:
   authentication, persistent audit log, per-user account binding, position
   checks, price bands, daily limits, idempotency, approval signatures and
   kill-switch behavior must be implemented.

## Running it locally

```bash
cd analysis
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api_server:app --reload --port 8088
curl localhost:8088/stock/recommendation/SAMPLE1
```

Example paper preview:

```bash
curl -X POST localhost:8088/orders/preview \
  -H 'content-type: application/json' \
  -d '{"code":"SAMPLE1","side":"BUY","quantity":100,"mode":"paper"}'
```

Then submit the returned `intent.id`:

```bash
curl -X POST localhost:8088/orders/submit \
  -H 'content-type: application/json' \
  -d '{"intentId":"<intent-id>"}'
```

Or run the recommendation pipeline standalone without HTTP:

```bash
cd analysis && python3 main.py
```

## Next build steps

1. Add persistent SQLite/Postgres audit storage for recommendations and order intents.
2. Add a formal risk-policy module (position size, price deviation, daily loss, kill switch).
3. Add authentication/user ownership to order endpoints.
4. Build a broker-adapter interface with a `PaperBroker` first; keep all real brokers disabled.
5. Locate the existing BIAP backend ingestion path and replace mock data with real TSETMC data.
6. Add CODAL normalization/fundamental ingestion.
7. Wire the mobile stock detail page to the recommendation endpoint.
