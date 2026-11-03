# Iran - feat/mobile-iran-20261103 (started 2026-11-03)
- Branch = live/base-20261030 + merge of fix/iran-codal-evidence-20261028 (Iran 1.0.7 baseline; clean merge).
- Investigation results (E, F, G, H, J) in `IRAN_FINDINGS_20261103.md`; JSON samples in `samples/`.
- App fixes (K, partial): `mobile/src/lib/signal-display.ts` + `tests/signal-display.test.mjs` (4 tests), wired into `recommendation-card.tsx` and the stock screen; `npm run test:ui`; `tsc --noEmit` clean.
- Not started: Iran company screen per-agent view (1a), AI Company Analysis and Audit Analysis in «بیشتر» (1b/1c), price provenance backend fix, inbox warm-up fix, remaining K items.

## 2026-11-03 08:36 UTC — BIAP_CODAL_INBOX enabled on biap-fin (owner-approved)
- Verified first: biap-fin open files = /var/lib/biap/market-memory.sqlite3, analysis/biap_audit.sqlite3, analysis/biap_performance.sqlite3 only; nothing under /var/lib/biap-global, ledgers or snapshots.
- Warm-up: no code change needed — the existing `BIAP_WARM_SYMBOLS` start-up warm-up primes the inbox cache. Drop-in `/etc/systemd/system/biap-fin.service.d/codal-inbox.conf` (BIAP_CODAL_INBOX + BIAP_WARM_SYMBOLS=پکرمان). Unit backup: ~/backups/biap-fin-unit-20261103 (mode 700). Rollback: delete the drop-in, daemon-reload, restart.
- Restarted only biap-fin at 08:35:59 UTC (outside 22:45–02:00). Ready in <10 s.
- Public API after: پکرمان call HOLD 0.122, dataSource=codal, fundamental vote +0.20 / conf 0.65 (before: BUY 0.273, fundamental weight 0). فولاد BUY 0.33 (codal=True); شپنا HOLD 0.023 (codal=False, no statements).
- Open: the first request after each nightly manifest change (~02:18 UTC) is cold again (~80 s) until a background rebuild is coded (needs deploy of code; held).
Sample: docs/mobile/samples/iran_pekarman_prod_after_inbox_20261103.json

## 2026-11-03 — Price provenance (Iran item e) built, NOT deployed
- New additive `analysis/price_provenance.py` + `priceProvenance` field on `GET /listed-companies/{code}`: stored price (7,170 / 2026-09-12 for Pekarman) and the newest market-memory observation are each labelled with source, observedAt, ageHours, status (fresh/stale/missing/unknown_time); disagreement is shown; the append-only 90-day market-memory history is listed. Nothing is overwritten or deleted. Fail-soft.
- Tests: tests/test_price_provenance.py (3) + existing listed-company tests, 15 passed (service venv).
- Not deployed: prod biap-fin runs the main checkout; deploying this branch needs a merge (held to 19 Nov unless owner approves). App does not read the field yet.

## 2026-11-03 — AI company analysis backend (1b), additive, NOT deployed
- `analysis/ai_company_analysis.py` + `GET /ai/company-analysis/{code}` (biap-fin, auth required) and `POST /global/ai-analysis` (Global; rate-limited per device — Global has no accounts; cannot be live before 19 Nov).
- Facts = stored analyses only; model told to use nothing else; INSUFFICIENT_DATA never calls the model; cache per (kind, symbol, UTC day, lang) in sqlite (BIAP_AI_CACHE_DB, default /var/lib/biap/ai-company-analysis.sqlite3); BIAP_AI_DAILY_LIMIT (default 10 fresh reports/user/day); BIAP_AI_BASE_URL configurable; probe request (cached 5 min) before use; key only from server env.
- Tests: tests/test_ai_company_analysis.py 5 passed.
- **Probe result today: the key in biap-fin's environment (and in .env.ai) is rejected by Anthropic with `authentication_error: invalid x-api-key`** (not a credit message). Reports can therefore not be generated until a valid key is put in the EnvironmentFile (mode 600). The app will show "AI unavailable".
