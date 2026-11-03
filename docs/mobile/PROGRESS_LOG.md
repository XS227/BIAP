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

## 2026-11-03 — Iran app: «تحلیل شرکت با هوش مصنوعی» + «تحلیل حسابرسی» screens (1b/1c)
- «بیشتر» now has both items. AI screen calls `/ai/company-analysis/{code}` (shows Persian state for INSUFFICIENT_DATA / AI_UNAVAILABLE / RATE_LIMITED, label «تولیدشده با هوش مصنوعی؛ توصیه‌ی سرمایه‌گذاری نیست»). Audit screen is pure client-side logic over the stored CODAL statements (`audit-analysis.ts`, 4 tests).
- Audit evaluates only what the importer stores: balance-sheet identity (data quality), net-margin change, leverage, equity trend, auditor opinion; accruals/CFO/Beneish/Altman/Zmijewski are INSUFFICIENT_DATA (no cash-flow/receivable/working-capital fields stored).
- **Data-quality finding:** for Pekarman report 1550679 the stored `total_assets_current` (161,431,776) and `total_liabilities_current` (129,035,244) do not satisfy assets = liabilities + equity (38,832,929), and differ from the figures read directly from the report earlier (340,995,803 / 302,162,874). The importer's asset/liability parse needs review; the Audit screen flags it.
- tsc clean; test:ui 8/8. The AI endpoint is not deployed, so the screen will show "unavailable" until it is.

## 2026-11-03 — Step 1: importer asset/liability parse (Pekarman), items (k) and (i)
**Parse root cause.** Production runs `main`, whose `codal_parser_v2` matches labels by *prefix*, so «جمع دارایی‌ها» matched «جمع دارایی‌های غیرجاری» (161,431,776) and «جمع بدهی‌ها» matched «جمع بدهی‌های غیرجاری» (129,035,244). The fix (exact-label match + `balance_sheet_check` BLOCK) already exists as a59d0b4 on `fix/iran-codal-evidence-20261028` (4 commits ahead of main) and is merged into this branch. History is untouched (the importer reads reports; nothing is deleted).
**Verified with the branch code against the real inbox (read-only, scoped path used by the API):**
- پکرمان — report 1550679, consolidated FY1404/12/29 audited: assets 340,995,803; liabilities 302,162,874; equity 38,832,929 (prev 201,439,750 / 147,879,863 / 53,559,887); balance check PASS both years.
- فولاد — report 1574326, consolidated FY1404/12/29 audited: assets 9,576,820,406; liabilities 4,446,892,738; equity 5,129,927,668; PASS.
- شپنا — no usable scoped (own/consolidated) statement in the inbox → honest "none"; the unscoped lookup returned only a subsidiary's report (راهبر ترابر انرژی), which the scoped path correctly refuses. Same for the unscoped فولاد hit (a sports-club subsidiary).
**Not live:** production still runs the old parser until the fix branch is merged to main (deploy-backend then deploys biap-fin). Needs owner OK (backend-merge rule).
**(k):** Taban +2175% root cause = pre-listing base price rows (close 1,000, priceFirst 0) inside the 400-day history plus the first-trade jump; `_history_performance` now skips untraded rows and restarts the series after any >25% single-session discontinuity (impossible under price limits). Also explains «annualized volatility 2358%». Test added (tests/test_tsetmc_enrichment.py). Taban market cap (6.78e15 rial from shares 3e11 × 22,610) is arithmetically consistent; the shares input needs a second source — NOT fixed. Numeric market id: new `displaySymbol` used in modules/bizdev/data/module screens. Confidence now shows the graded-sample count / "thin record" note. DATA HOLD, neutral portfolio button, 100% weights, queue badge were done earlier.
**(i):** misleading LIVE/AUTO/DEMO/LISTED LIVE badges replaced by Persian statuses (`data-status.ts`: تأییدشده / قدیمی / موجود نیست / خطا در دریافت); stock screen shows CODAL and extended-market status rows. Search by «پکرمان» and the numeric id was verified earlier.
Tests: mobile test:ui 12/12, tsc clean; analysis 50 passed (enrichment, CODAL evidence gate, kiasha).

## 2026-11-03 (Iran 1.0.9, owner phone-test fixes on feat/mobile-iran-20261103; no backend merge/deploy)
- Diagnosis (A): app calls only https://biap.dadashi.no/api -> nginx -> biap-fin :8088 (this server, PR #68 live). Taban/Foolad/Shepna/5 test companies were not on the Liara request list (only never-enriched backlog); listed-companies detail returns stored company.codal = None for Taban/Pekarman/Foolad. Request list: priority.txt now پکرمان, تابان, فولاد, شپنا, سپیدار, مبین, فخوز, دلقما, چکاپا (backup priority.txt.bak-20261103).
- App: module data falls back to the recommendation's verified CODAL fundamentals when the stored record has none; Tindex removed from all UI text/sources; research-five screen and links removed; modules receive the InsCode + name (no more «نماد نامشخص»); search ranks ordinary shares before bonds/funds/rights and shows the instrument type; symbol picker in AI Analysis and Audit + buttons on the symbol page; 60-day chart only from the last >25% jump (else «داده کافی نیست»); Persian wording for evidence status/reasons and agent reasoning; last-session title/date when the market is closed; login hint to turn the VPN off.
- Checked: SMTP login to the configured server works (465/TLS). The reset-email send result is discarded by the backend (no sent/failed log), so sending of an individual mail cannot be proven from logs.
- Tests: tsc clean; test:ui 18 pass. Version 1.0.9 / versionCode 10. Update manifest NOT changed.
- 1.0.9 build OK (EAS run 41669508157, commit 21e8004): BIAP-1.0.9-Expo-EAS.apk sha256 3beaa7d6e159e197422ef08da8d2e3031b5297929db7ea8c0d3c7f774f1d6350, served temporarily at https://biap.dadashi.no/dl/f98syxug/iran109.apk (delete with the other /dl files after install). Backend item 3 = draft PR #75 (not merged, not deployed). Update manifest untouched.

## 2026-11-03 — Iran 1.0.10 (app branch only; no backend merge/deploy)
- Picker/EDA «تابان25»: data-connect list (backend listed-companies, unfiltered) now ranks ordinary shares first, shows instrument type, and a stored bond/fund selection is dropped. InsCode + symbol name passed to modules from data-connect, modules, bizdev (fixes «نماد نامشخص»).
- AI Company Analysis HTTP 404 (endpoint not on production main): shows «این بخش به‌زودی فعال می‌شود.»
- Audit: no risk score when fewer than 6/10 checks evaluated; coverage shown; missing checks grouped in one card (removes the contradictory duplicate leverage-style cards).
- Operating cash flow for Pekarman: the CODAL HTML in the inbox (tracing 1541525) DOES contain the consolidated cash-flow statement (CFO 41,497,665 vs 28,042,248, million-rial units as filed), but analysis/codal_parser_v2.py only extracts revenue, net profit, gross profit, assets, liabilities, equity — no cash-flow/receivables/PP&E/depreciation/current-items aliases, and CodalFundamentals has no such fields. Fix is backend (parser + dataclass + API); not done (held).
- Tests: test:ui 20 pass, tsc clean. app.json 1.0.10 / versionCode 11.
- 1.0.10 build OK (EAS run 41720313621, commit 7d3382a): BIAP-1.0.10-Expo-EAS.apk sha256 2cc2a712ca5244541d9909e6b8e88c1b474ca5283117763aabf4420cdf8e516b, temporarily at https://biap.dadashi.no/dl/f98syxug/iran1010.apk. Manifest untouched; PR #75 still draft.
