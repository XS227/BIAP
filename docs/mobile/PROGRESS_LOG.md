# Mobile apps progress log (task file: /tmp/fc378dd4-...txt) - started 2026-11-03

Rules: branches from live/base-20261030 in separate worktrees; no merge of backend PRs before 2026-11-19; new endpoints additive only; nothing on production; stop at Checkpoint 1.

## Global - feat/mobile-global-20261103
- 02:05 UTC step 0 locate report: `docs/mobile/STEP0_LOCATE_20261103.md`.
- 1d "Trade at a Broker": `src/config/brokers.ts` (single config: IBKR, Nordnet NO/SE/DK/FI, Saxo, DEGIRO, Trading 212), `src/lib/broker-handoff.ts` (market filter, public URL only, no pre-fill because no public instrument deep link is verified), `src/app/broker.tsx` (More menu item + "Trade" button on the company screen, leave-BIAP confirmation with the exact notice). No credential fields, no trading API. 6 new tests; test:api 25/25; `tsc --noEmit` clean (added `allowImportingTsExtensions` so the node test runner and tsc agree).
- Note: `expo lint` is not configured in this repo (it auto-installs eslint on first run); it reports 17 pre-existing errors in files not touched here. I did not commit the auto-added eslint config/deps.
- 1c "Audit Analysis" (Global): `src/lib/audit-analysis.ts` (accruals, profit vs operating cash flow, Beneish M-Score, Altman Z″/Zmijewski from stored Agent 9, auditor opinion), `src/app/audit.tsx`, More menu item. Each check shows inputs, period, source; INSUFFICIENT_DATA when missing; "risk score" only (never a rating); banks/insurers excluded from accruals/Altman/Beneish. 11 tests; test:api 34 total; tsc clean.
  - Real API (POST /global/analyze, read-only analysis): AAPL (US), SAP (DE Xetra, ISIN DE0007164600 matches), HSBA (GB LSE, ISIN GB0005405286 matches). All six Global agents return non-null votes and confidence. Beneish and auditor opinion are INSUFFICIENT_DATA for all three because the stored values hold one reporting year (plus revenue_prev) and no `audit_opinion`. That is the honest result, not a bug.
  - `analyzedAt` is null on production responses: the scan-time stamping is on the fix branch and not deployed (by design, before 19 Nov).
- 1a Global company screen: audit result = it already shows the six agents (vote, confidence, reasoning, "No verified inputs" state), Kiasha final call, Evidence, Agent 8/9/10, valuation, fundamentals and evidence sources. Gap closed here: a statement-status line above Fundamentals (`src/lib/statement-status.ts`: period, filing date, stored date, age, reporting currency, source, partial coverage; explicit INSUFFICIENT_DATA with no estimates). 3 tests; test:api 37 total.

## 2026-11-03 — Broker coverage re-verified from official pages (owner request)
- Only markets confirmed on each broker's own page stay in `brokers.ts`; each has `coverageSource` + `coverageNote`. Unconfirmed markets are not offered. Screen shows "Availability may vary; check the broker's site."
- Nordnet: NO/SE/DK/FI (nordnet.no trading-venues page). DEGIRO: all 12 (products-and-markets). Trading 212: US, GB, DE, FR, IT, NL, ES, PT (help-centre hours article; varies by entity). Saxo: US, FR, NL, PT only (page names main US + Euronext Amsterdam/Lisbon/Paris; "25+ countries" unlisted). Interactive Brokers: only FR — official pages return HTTP 403 to automated fetch; the rest is NOT confirmed. Owner: open the IBKR exchange list in a browser and add markets.
- Tests: test:api 38/38, tsc clean.

## 2026-11-03 — Global app: "AI Company Analysis" screen (1b)
- More → AI Company Analysis; calls `POST /global/ai-analysis` (additive backend route on feat/mobile-iran-20261103, not deployed; Global services cannot be restarted before 19 Nov, so the app shows "not available on this server yet" on HTTP 404). Shows INSUFFICIENT_DATA / unavailable / rate-limit states honestly and the label "AI-generated, not investment advice". No key in the app.
- tsc clean.
