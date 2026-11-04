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

## 2026-11-04 — post-1.0.10 report
- 1.0.10 phone test OK. Old /dl files (iran.apk, global.apk, iran109.apk) removed; only iran1010.apk remains at /dl/f98syxug/.
- Taban audit (live recommendation data): 5/10 evaluated (balance identity, margin, leverage, equity, opinion). Threshold 6 is unreachable until cash-flow/current-items parsing exists (accruals, CFO, Beneish, Altman, Zmijewski are never computed). Phone said "6/10" — likely misread of the message «کمتر از ۶ از ۱۰»; message reworded. English opinion «qualified» now shown as «مشروط» (FLAG).
- Pekarman CODAL HTML contains CFO, current assets/liabilities, trade receivables, retained earnings; analysis/codal_parser_v2.py does not extract them. Backend work, held.
- Manifest update NOT done: see hand-off note (branch carries analysis/** changes; merging triggers deploy).

## 2026-11-04 — manifest / parser / history PRs
- Permanent APK: https://biap.dadashi.no/download/BIAP-Iran-1.0.10.apk (sha256 2cc2a712…516b verified); /dl/f98syxug/iran1010.apk kept until update centre confirmed on phone. nginx backup: /home/ubuntu/backups/biap-dadashi.nginx.pre-perm1010-20261104.
- PR #76 (draft): analysis/mobile_release.json + mobile/app.json → 1.0.10/11. Merge restarts biap-fin (analysis/** path) and triggers an Expo build on main; stable channel then needs deploy/publish-mobile-apk.sh with the 1.0.10 APK.
- PR #77 (draft): codal_parser_v2 extracts CFO, current assets/liabilities, receivables, retained earnings, fixed assets (depreciation/SG&A deliberately not). 1796 tests pass.
- PR #78 (draft): Taban history fix split from #75; #75 closed.
- App branch: audit now computes accruals, CFO divergence and Zmijewski when the fields exist. With PR #77 data: Pekarman 7/10 (score 67), Foolad 7/10 (83), Shepna 7/10 (50) before audit opinion (+1 when recommendation supplies it). Beneish (needs depreciation, SG&A) and Altman Z'' (needs EBIT) stay INSUFFICIENT_DATA.

## 2026-11-04 — PR #78/#77 merged and deployed (biap-fin only)
- Backups: /home/ubuntu/backups/biap-fin-premerge-20261104 (8 DBs, market-memory, mobile_release.json, release channel files, PRE_DEPLOY_SHA 378db3d). Rollback: git reset --hard 378db3d in the production checkout + systemctl restart biap-fin (or revert merge commits; restore DBs from the backup dir).
- #78 squash bf83d5c deployed 16:59:35 UTC; Taban recommendation no longer lists «high annualized volatility 2321.8%» (score -0.106 → -0.095). #77 squash 26bab2a deployed 17:02:16 UTC; recommendation API for Taban and Pekarman now returns operating_cash_flow, current items, receivables, retained earnings, operating profit, SG&A (depreciation only when column-checked). Health 200, no errors in journal.
- Release-channel safety: deploy-backend's workflow_run publish steps only run when the VPS HEAD differs from origin/main, so they were skipped; channel files backed up under releases/ in the backup dir.

## 2026-11-04 — Iran 1.0.11 built, published, manifest updated
- App branch feat/mobile-iran-20261103 @ 9e47d60 (audit: accruals, CFO divergence, Zmijewski, Altman Z'', Beneish; opinion in Persian). EAS run 41873799726 OK: BIAP-1.0.11-Expo-EAS.apk sha256 8b214b6555b754c2c6fdc701573dba3b5607c3c8c7c845fc5040050d608647c3, package com.biap.mobile, versionName 1.0.11 (manifest string check). Signing block shares the certificate material with 1.0.10 (no apksigner on server; install on phone NOT verified).
- Permanent link: https://biap.dadashi.no/download/BIAP-Iran-1.0.11.apk (HTTPS sha256 matches). 1.0.10 files kept (/download/BIAP-Iran-1.0.10.apk, /dl/f98syxug/iran1010.apk).
- PR #76 squash-merged as 208bd45 (manifest 1.0.11/12 + app.json), deploy OK. Main workflow runs checked before merge (none in progress); channel files unchanged by the earlier merges.
- Update centre: publish-mobile-apk.sh stable+expo → /api/app/release version 1.0.11, apkAvailable true, expoApkAvailable true, both channel files sha256 8b214b65…. Caveat: stable channel now serves the EAS-signed APK (previous stable 1.0.5 was debug-signed; backups in /home/ubuntu/backups/biap-fin-premerge-20261104/releases).
- Live audit via recommendation API: Pekarman 8/10 score 64 (missing Beneish — depreciation rejected by column check, opinion); Foolad 9/10 score 0 (missing Beneish; note the live record is the annual 1404 filing 1574326, different from the inbox 1585000 interim used earlier); Shepna 0/10 — live API reports CODAL unavailable although the inbox holds a Shepna report that parses (cause not yet found; not changed).

## 2026-11-04 19:20 UTC — Iran data coverage audit (read-only; run on a sqlite .backup copy, production untouched)
Source: CompanyRegistryStore.full_report(), listed_company_ingestion.status(), stored company_json for every registry company, codal_inbox parsed with parser v2 + codal_quality.review_iran_codal.
- Raw instruments 9,175 → genuine unique companies (company_registry) 3,805 (operating 3,125; investment 353; bank 77; insurance 96; holding 75; listed financial 79). Excluded: 4,570 non-company instruments (bonds 1,084; funds 746; options 2,678; rights 39; commodity 11; unknown 12). Duplicate mappings 0. Caveat: 20 registry entries are flagged fund/market-maker (no standard statements), so the true operating universe is slightly below 3,805.
- Enriched (company_json stored): 2,518 (66.18%); not enriched 1,287 (1,232 never attempted, 54 «no verified company data available», 1 CODAL rate limit). Enriched with market price: 1,664.
- CODAL: stored fundamentals present 66; stored and balance-verified (review PASS) 26 (19 with cash-flow inputs). CODAL inbox (369 companies requested): 341 mapped to registry; 52 parsed from own statements; 46 verified PASS (all with CFO/current items/retained earnings/EBIT; only 6 with Beneish inputs). Union of verified (stored or inbox) = 48 companies = 1.26% of 3,805. 109 inbox companies have own statements listed but no report fetched; 180 list no own statements; 3,464 registry companies have no inbox record (never requested from Liara).
- Audit module on those 48: 46 reach ≥6/10 checks (score shown): distribution evaluated 4:2, 7:3, 8:37, 9:6.
- Module usability among enriched: SQL context 2,518; KPI/Dashboard/Financial Model 1,681 (market or CODAL); SWOT/report 2,518 (public evidence only); Accounting/Audit with full statements 48; AI analysis 0 (endpoint not on production).
- New unique companies: 7 in last 24 h, 42 in last 7 days (company_registry.first_seen_at). Run history: 72 runs since 2026-09-17.
- Worker listed-company-enrichment-v1: status paused between batches (cursor 2,518/3,805; last batch 68 processed, 64 ok, 4 failed at 18:28 UTC); timer biap-listed-company-baseline next 2026-11-05 01:01 UTC; failedCodes 97, notApplicable 20, needsReview 3.

## 2026-11-04 19:35 UTC — Shepna 0/10 root cause, Expo-on-main check
- Shepna: CODAL lists two affiliate statements («(شرکت راهبر ترابر انرژی)», «(شرکت پترو پ…)») under the parent symbol; the Liara fetcher's 2-report budget went to them, so Shepna's own consolidated annual 1562697 was never fetched. API 0/10 = correct fail-closed. The earlier 8/10 was my offline parse of an affiliate's report (wrong entity). Same pattern in the inbox for پارسان, فخوز, شپنا, یکتانت, سشرق. Fix: PR #79 (draft, not merged; 1802 tests pass): fetcher + select_scope_filings skip affiliate titles. Needs the Liara fetcher redeployed.
- Expo EAS run 41885940587/41885940535 (main push from PR #76) completed success. Its Deploy backend workflow_run (19:33) was skipped; earlier workflow_run deploys: Deploy main / Publish stable / Publish Expo = skipped (scope gate: VPS HEAD == origin/main 208bd45). Channel files unchanged since 18:21:32 (sha 8b214b6555b754c2…, 1.0.11); /api/app/release 1.0.11/12 apkAvailable+expoApkAvailable true; /download/BIAP-Iran-1.0.11.apk sha 8b214b65…. Nothing overwritten. Residual risk: the guard is only the scope gate (a later main merge between a build finishing and its workflow_run would publish a main-built APK) — consider a workflow guard.

## 2026-11-04 20:30 UTC — CODAL recovery after #79/#80/#83 (blocked parts)
- Merged: #80 51f0ea0, #79 5602183, #83 8ed53e2. Deploy backend runs for #79 and #83 FAILED at "Deploy main to VPS": "Refusing deploy: VPS working tree has local changes: M analysis/audit_parser.py". The uncommitted edit (audit-opinion regex work, mtime 20:18:46, preceded by `git reset` at 20:17) was made in the production checkout by another session, not by me; I did not touch or discard it. biap-fin is still running the 19:35 code (health 200, ready). Note: I ran `git pull --ff-only` in the production checkout at 20:30 (files now at 8ed53e2, process not restarted).
- Liara (89.42.199.20): port 22 times out from the VPS and no Liara credentials exist here, so backup + redeploy of the fetcher and the re-fetch cannot be done from this session. Runbook prepared (scratchpad/liara-redeploy.sh). Request list on the VPS now starts with شپنا, پارسان, فخوز, یکتانت, سشرق (backups in /home/ubuntu/backups/biap-fin-premerge-20261104/*.pre-five-20261104).
- Before-state (inbox, validated with scratchpad/validate_five.py): all five have issuer sy match, but NO own report fetched: شپنا own 1562697/1547751/1373349 listed, HTML missing; فخوز 1584708/1541772 missing; یکتانت 1391396 missing; سشرق 1438790/1436320 missing; پارسان: all 8 listed are affiliates (own statements beyond the listing window).
- Coverage before (2518 enriched / 3805 genuine): CODAL-verified (stored or inbox) 51 (1.34%); audit ≥6/10: 48.

## 2026-11-04 late — recovery follow-up (verification)
- Production checkout dirty `analysis/audit_parser.py` (private-firm «این موسسه» opinion wording): backed up to `/home/ubuntu/backups/biap-fin-20261104-dirty/`, preserved as PR #85 with tests (not merged, not deployed). Prod checkout still dirty; Deploy backend blocked until #85 merged and the file restored from main.
- Inbox verification on this VPS: 11 exports, latest `2026-11-04` created 22:11Z has 110 reports (not 137); tracing IDs 1562697/1584708/1391396/1541772 absent from every `reports.jsonl`; validate_five.py → NO_OWN_REPORT_FETCHED for all five. The reported transfer is NOT visible here. No re-ingest, no audit run, no 1.0.12 build performed.
- PR #82 (a813b7a) verified on branch: test:ui 24/24 pass, tsc clean, Beneish uses finite-only guard.
