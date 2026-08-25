# BIAP — Project Status (analysis/backend side)

_Last updated: 2026-08-25_

This repo is the analysis/decision layer for BIAP. It's separate from
[`-biap-mobile`](https://github.com/nasrindadashi-cloud/-biap-mobile), which
owns the Expo/React Native app and already talks to a live backend at
`https://biap.dadashi.no/api` (server `89.42.199.20`).

**Nothing here is deployed or wired into the live backend yet.** This is a
working prototype ready for integration.

## What this is

An intelligent financial/business analysis pipeline for Iranian equities:

```
CODAL (disclosures/reports) ─┐
                              ├─> normalize/store ─> agent team ─> Kiasha ─> Buy/Hold/Sell
TSETMC (price/volume/P-E) ───┘
```

- **`analysis/agents.py`** — 4 analyst agents (fundamental, risk, forecast,
  comparison), each returns a vote (-1..+1), confidence and reasoning.
- **`analysis/kiasha.py`** — trust/maturity-weighted decision layer that blends
  the agent votes into BUY/HOLD/SELL.
- **`analysis/data_sample.py`** — mock CODAL + TSETMC data for a fictitious
  company until real ingestion is connected.
- **`analysis/api_server.py`** — FastAPI wrapper for recommendation, guarded
  execution, risk status and audit inspection.
- **`analysis/execution.py`** — execution-policy boundary. PAPER and APPROVAL
  only; AUTO is explicitly blocked in code.
- **`analysis/audit_store.py`** — durable SQLite order-intent + append-only audit
  event storage. DB path is configurable with `BIAP_AUDIT_DB`.
- **`analysis/risk.py`** — independent risk-policy engine with kill switch,
  quantity/notional limits, price-deviation checks, daily notional limit and
  recommendation-strength gates.

## Implemented API prototype

### Recommendation

```
GET /stock/recommendation/{code}
```

Returns the current Kiasha BUY/HOLD/SELL decision with weighted score and agent
breakdown.

### Execution — PAPER / APPROVAL only

```
Recommendation
     ↓
Risk Policy
     ↓
Execution Policy
     ↓
Persistent Audit Store
     ↓
Paper / Approval
     ↓
Future Broker Adapter
```

Implemented:

- `POST /orders/preview`
  - recalculates the current recommendation;
  - evaluates independent risk policy before creating an intent;
  - rejects requests when the kill switch is active;
  - enforces max quantity, max order notional and max daily notional;
  - checks optional limit price against the TSETMC-style reference price;
  - checks BUY/SELL recommendation strength;
  - rejects contradictory BUY-vs-SELL execution policy requests;
  - persists accepted intents in SQLite;
  - records both accepted and rejected attempts as audit events;
  - `paper` creates a simulation intent;
  - `approval` creates `PENDING_APPROVAL`;
  - `auto` remains explicitly blocked.
- `POST /orders/submit`
  - reads the intent from persistent SQLite instead of process memory;
  - `paper` returns `PAPER_FILLED` with a paper broker-order id;
  - `approval` remains `PENDING_APPROVAL`;
  - persists the resulting receipt and audit event;
  - never sends a request to an external broker.
- `GET /orders/{intent_id}` — reads a persisted intent/receipt.
- `GET /audit/orders?limit=...` — recent persisted order intents.
- `GET /audit/events?limit=...` — append-only execution/risk audit events.
- `GET /risk/status` — effective policy snapshot + today's tracked notional.
- `/health` reports persistent audit + risk policy enabled, AUTO disabled and no
  broker connected.

### Risk configuration

Risk limits are deployment-configurable without editing code:

- `BIAP_KILL_SWITCH` — global stop (`false` by default).
- `BIAP_MAX_ORDER_QUANTITY` — default `100000`.
- `BIAP_MAX_ORDER_NOTIONAL` — default `2000000000`.
- `BIAP_MAX_DAILY_NOTIONAL` — default `5000000000`.
- `BIAP_MAX_LIMIT_DEVIATION_PCT` — default `5`.
- `BIAP_MIN_BUY_SCORE` — default `0.10`.
- `BIAP_MAX_SELL_SCORE` — default `-0.10`.
- `BIAP_AUDIT_DB` — optional SQLite path; defaults to
  `analysis/biap_audit.sqlite3`.

The local SQLite database and WAL files are gitignored.

## How this is meant to plug into `-biap-mobile`

The existing mobile `GET /stock/watchlist` contract remains unchanged. The
recommendation endpoint is additive and can be called from
`src/app/stock/[code].tsx` alongside the current watchlist data.

Future execution UX should remain additive:

1. Show FIN recommendation.
2. User opens order preview.
3. BIAP calls `/orders/preview`.
4. Risk policy must pass.
5. Paper mode simulates only.
6. Approval mode waits for explicit approval; no real broker adapter exists yet.
7. AUTO remains disabled until separately approved and production-hardened.

## Open blockers

1. **CODAL/TSETMC ingestion is unresolved.** The prototype still uses mock data.
   The existing BIAP backend at `89.42.199.20` already serves TSETMC-derived
   watchlist prices, so locating/reusing that ingestion path remains the fastest
   route to live data.
2. **No trading/order API confirmed.** Broker research in Discussion #1 remains
   preliminary; no broker credentials or confirmed order API are present.
3. **`TRACK_RECORDS` in `kiasha.py` are placeholders**, not real per-agent
   performance history.
4. **Authentication/account ownership is not built yet.** Audit data is durable,
   but order endpoints are not yet bound to authenticated users/broker accounts.
5. **Risk policy is intentionally incomplete for live money.** It now has
   quantity/notional/price/recommendation/kill-switch controls, but live trading
   would still require position ownership checks, daily realized-loss limits,
   idempotency keys, approval signatures, market-session rules, stale-quote
   checks and production monitoring.
6. **No real broker adapter exists.** `PAPER_FILLED` is still generated by the
   execution service itself, not through a broker-interface abstraction.

## Running it locally

```bash
cd analysis
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api_server:app --reload --port 8088
curl localhost:8088/stock/recommendation/SAMPLE1
```

Risk status:

```bash
curl localhost:8088/risk/status
```

Example paper preview using the mock reference price (`18420`):

```bash
curl -X POST localhost:8088/orders/preview \
  -H 'content-type: application/json' \
  -d '{"code":"SAMPLE1","side":"BUY","quantity":100,"limitPrice":18420,"mode":"paper"}'
```

Then submit the returned `intent.id`:

```bash
curl -X POST localhost:8088/orders/submit \
  -H 'content-type: application/json' \
  -d '{"intentId":"<intent-id>"}'
```

Inspect the durable audit trail:

```bash
curl 'localhost:8088/audit/orders?limit=20'
curl 'localhost:8088/audit/events?limit=50'
```

## Next build steps

1. Add authentication/user ownership to all order/audit endpoints.
2. Add idempotency keys and explicit approval signatures/state transition.
3. Build a broker-adapter interface and move paper fills into `PaperBroker`.
4. Add position/exposure checks and realized daily-loss limits to the risk engine.
5. Locate the existing live BIAP TSETMC ingestion path and replace mock market data.
6. Add CODAL normalization/fundamental ingestion.
7. Wire the mobile stock-detail page to recommendation and paper-order preview.
