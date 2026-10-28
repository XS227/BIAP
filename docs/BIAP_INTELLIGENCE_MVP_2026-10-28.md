# BIAP Intelligence MVP (2026-10-28) — research branch only

Branch: `feat/biap-intelligence-mvp-20261028`, based on `feat/biap-global`.
The Iran production main branch, Global production deployment, frozen 2026-10-20 paper portfolio and historical investment/DMA decisions are **not changed**.

## Implemented

1. `POST /global/intelligence/dashboard` accepts the exact existing Global `InstrumentRequest` shape and returns a read-only KPI snapshot, existing Kiasha decision, agent signals, evidence diagnostics, filing periods and source links.
2. `POST /global/intelligence/ask` accepts `{"instrument": {...}, "question": "...", "language": "fa"}` for grounded single-company Persian/English questions covering revenue, profit, debt, cash, cash flow, valuation, risk, evidence and the existing decision.
3. `GET /global/intelligence/preview` serves a standalone responsive bilingual research page bound to the same endpoints.
4. Regression tests: `analysis/tests/test_global_intelligence.py`.

The response explicitly reports `generativeModelUsed=false` and `method=deterministic_grounded_preview`: this is **not** an unrestricted LLM assistant, a whole-market natural-language screener, or a forecast. Unsupported questions return a supported-topics message rather than inventing an answer.

## Data and evidence guarantees

- Runs the existing `_seed` authoritative listing check and `analyze_company` pipeline; no custom data provider, scrape, crawler, market scan, or new investment scoring is introduced.
- Uses existing `fundamentalEvidence` and `company` normalized fields; does not fabricate absent values, substitute zero for null, or synthesize a history.
- Filing status, period and market price timestamps are separate. An official filing at the company level does **not** verify every displayed field: normalized results may include vendor supplements. KPI objects therefore carry `fieldVerified=false`, and the UI repeats this limitation.
- The existing decision and score are reported unchanged, and no orders, portfolios, snapshots, caches, or existing historical artifacts are modified.
- Preview is flagged read-only and has `noindex` metadata; publishing it should require a deployment approval and appropriate API rate limits.

## Example

```bash
curl -X POST http://localhost:8097/global/intelligence/dashboard \
  -H 'Content-Type: application/json' \
  -d '{"country":"US","exchange":"NASDAQ","ticker":"AAPL"}'

curl -X POST http://localhost:8097/global/intelligence/ask \
  -H 'Content-Type: application/json' \
  -d '{"instrument":{"country":"US","exchange":"NASDAQ","ticker":"AAPL"},"question":"درآمد شرکت چقدر است؟","language":"fa"}'
```

## Validation and pending

- Python AST parsing passed for the new service, routes, API registration and regression test module.
- Core smoke checks passed for dashboard, missing debt, Persian/English answers and unsupported questions.
- Preview JavaScript syntax passed via `node --check`.
- **Full pytest and integration tests against live provider fixtures remain pending**; do not treat the preview as production-ready or deploy it without testing in a separate staging environment.

## Next increments (not part of this implementation)

- Auth/rate limits and per-request resource budgets; safe caching keyed by provider freshness.
- UI parity inside the mobile app and improved country/exchange selectors.
- Field-level provenance when all upstream adapters supply it, rather than treating an entire normalized filing as field-verifiable.
- Permissioned LLM/tool-calling with retrieval and citations, no unconditional trading advice.
- Later: scenario engine and BIAP Enterprise ERP connectors as separate licensed/consented products, only after their own validation.
