# PROGRESS_LOG

## 2026-11-02 — P1.12 liquidity gate (branch `fix/biap-fix-plan-20261102`)
- Done (tests first, v2 only): directional liquidity vote removed; USD 100k tradability gate (BUY/ACC -> HOLD, "نقدشوندگی کم"); unknown liquidity -> "نقدشوندگی تأیید نشده", BUY -> ACCUMULATE; DE gate disabled pending Xetra volume check (added to P2.1). 1976 tests pass.
- Measured: tier counts before/after for US/DE/NO and SELL -0.10 margin (not implemented) in `docs/P1_12_LIQUIDITY_MEASURE.md` section 4.
- Flag for owner: Norway loses all 9 BUYs (no usable volume); gate uses mean, not median, daily value; production/live untouched, nothing deployed or pushed.
- Next: owner decision on Oslo volume data and on deploy; P2.1 Xetra volume verification.

## 2026-11-02 (later) — owner decisions after P1.12
- Pushed 05f4ed6 to origin/fix/biap-fix-plan-20261102 (fast-forward from 9f0f0a3; nothing else pushed).
- SELL -0.10 margin stays unimplemented (0.0); measurement (5 of 399) recorded in the changelog.
- Oslo volume data added to P2.4; Norway keeps labelled ACCUMULATE. New P2.8 (30-day daily volume series -> median) added.

## 2026-11-02 (continued) — remaining Phase 1, P2.1, P2.3
- P1.8 done (v2, tests first, `tests/test_p18_capital_intensive_distress.py`): Altman Z'' alone no longer sets the safety gate for Energy/Utilities/shipping; reasoning names the governing model. Sector list is my choice, owner to confirm. Changelog row added.
- P1.7 measured only (`docs/P1_7_SCORE_DISTRIBUTION.md`): BUY floor 0.25 is at p99+ (DE max 0.250). Recommend percentile-based floor behind v2; needs owner decision (protocol deviation). No threshold changed.
- P2.1 Xetra volume check done (`docs/P2_1_XETRA_VOLUME_CHECK.md`): Yahoo-based volume matches the official Deutsche Boerse post-trade file (median ratio 0.89, SAP 431M vs 411M EUR); ~50 % of Xetra names really trade under EUR 100k/day on the venue (median mcap 46M). Venue-only caveat noted. DE removed from the gate exemption (v2), test updated. DE statement-parsing fix (the 91 % rejection) is NOT done.
- P2.3 not started: `oam_esef.py:1422` skips interim statements on purpose and Norwegian interim reports are not ESEF-tagged, so this needs a new source (Oslo Newsweb PDFs / vendor) and a parser for trailing-12-month figures; scope and source need an owner decision before code.
- P1.1 tail / P1.3 reviewer workflow still open. Tests: 1931 pass (excluding the 4 known TestClient-hanging files). Committed locally, not pushed; nothing deployed.

## 2026-11-02 (owner round 2)
- Pushed 3654e59 to origin/fix/biap-fix-plan-20261102.
- P1.8: Real Estate/REIT added to the guard (test-covered). Banks/insurers: Agent 9 returns NOT_APPLICABLE (generic models suppressed); only negative equity or a going-concern warning block; unchanged.
- P1.7 implemented in v2 (pool PASS + conf >= 0.45; BUY top 10 % & score >= 0.10; ACCUMULATE top 25 % & >= 0.05). Before/after: NASDAQ BUY 175->159, NYSE 134->126, DE 13->14, NO 5->5; none over 30 %.
- Found: production ECB rate file ends 2026-10-13, so under v2 every non-USD market would have unknown liquidity (no BUY). Not touched in production; needs `fx_history` refresh + a timer. This also corrects P2.4 (Oslo volume exists).
- P1.3: REVIEW -> HOLD_OR_WATCH "needs review" in v2, `/global/review-list`, app line; tests added, P1.5/P1.6 tests adjusted.
- P2.3: Newsweb parser not built; `docs/DATA_VENDOR_OPTIONS.md` written (figures unverified, from web search only).
- P2.1: stock screen label "Xetra only"; DE statement diagnosis written (source has no cash-flow data); no parser code, needs owner option.
- Committed locally, not pushed; nothing deployed.

## 2026-11-02 (owner round 3)
- Pushed d17a968.
- ECB file: backed up (sha256 prefix c8c7794c...), refreshed in place via `python -m global_markets.fx_history refresh` (prod venv, prod data dir); nothing restarted. History: no timer/cron existed (checked `systemctl list-timers`, user crontab, /etc/systemd, deploy scripts); the file came from one manual refresh on 2026-10-14. Timer unit pair written to `/home/ubuntu/claude-tmpdir/claude-1000/-home-ubuntu/a3d4cac7-9880-4554-a3f9-f76270cd2cd4/scratchpad/install-ecb-timer.sh`; **owner must run it with sudo** (`! sudo bash <that path>`). Changelog row written with the verified counts; the proposed wording "affected v1 inputs" was NOT used because the count shows none (0 of 537 conversion rows have a period end in the stale window).
- Germany and P2.3: current rule stays (core cash-flow field required; BF key-data source has none; interim reports not read). Documented in `docs/P2_1_DE_STATEMENTS_DIAGNOSIS.md` and `docs/DATA_VENDOR_OPTIONS.md`. Waiting for the vendor choice.

## 2026-11-02 (round 3, continued)
- P1.1 closed (v2 evidence in changelog). P2.2: ESEF dividend/current-subtotal fallbacks + DE reviewed schema (tests: tests/test_p22_esef_current_dividend.py; 1943 pass). SAP reviewed values and index beta not done.
- Phase 3: five wording/format fixes in mobile-global (tsc clean, test:api 26 pass).
- P2.4 not started this round: its six items (isolated EU jobs, trading-calendar stamping for NASDAQ, official-close timestamps, analysis-stale flag, sync-derived dates, Global Top 10) each need production data/pipeline work; the per-market isolated runner already exists in /usr/local/bin/biap-global-price-refresh (one market per driver call). Next candidate: analysis-stale flag.

## 2026-11-02 (owner round 4)
- Pushed 2d6bb20 and a0e22b8. Standing rule: push the fix branch after each commit.
- ECB timer units + installer moved to `deploy/systemd/` and `deploy/install-fx-refresh-timer.sh`; owner runs it with sudo after reading it. Changelog row now states v1 was unaffected (period-end-date rates).

## 2026-11-02 (P2.4 start)
- US trading calendar: `us_holidays`, XNAS/XNYS in `session_calendar`; Nasdaq screener quotes stamped with the last completed session (`tests/test_us_session_date.py`, 1915 pass excl. TestClient files). Not deployed; takes effect at the next US refresh after deploy.
- Isolated EU jobs: already implemented in the production runner (per-market lines); the 30 Oct failure was Milan DEADLINE only. Remaining work (status file, one retry, versioning the runner) listed in the plan.
- Not started: official-close timestamps (Yahoo daily bar is stamped at the session open, 08:00 UTC for DE/NO, 13:30 UTC for US), analysis-stale flag, sync-derived dates, Global Top 10.

## 2026-11-02 (P2.4 continued)
- FX timer installed by owner (next run 16:32:58 UTC); first-run check scheduled after 16:35 UTC.
- Official-close stamp: `yahoo_chart._session_close_at` replaces the daily-bar stamp (session OPEN, 08:00 UTC DE/NO, 13:30 UTC US) with the venue's regular-session close on the bar's local date (time-of-day from `currentTradingPeriod.regular`; early-close days are stated at the nominal close). A session still open keeps `regularMarketTime`. Basis recorded in `raw_provider_fields.price_time_basis`. Date part unchanged, so no freshness-by-date effect. Tests: `tests/test_yahoo_session_close_stamp.py`. Not deployed.

- Analysis-stale flag: `decision_overlay.analysis_staleness` adds `analysisStale`, `analysisStaleDays`, `analysisAsOf`, `priceAsOf` to each investment-view row when the ledger's dated stage-1 quote falls on a later UTC day than `analyzed_at` (same-day and undated quotes are never flagged; the sync time is not used). Label only: tier/score/confidence unchanged. App shows "Outdated analysis - price is newer (N d)" through `investmentBadge`. Tests: `tests/test_analysis_stale_flag.py`, `mobile-global/tests/analysis-stale.test.mjs`. 2008 Python tests pass; app test:api 28 pass, tsc clean. Not deployed. Re-analysis on price change is not built (flag only).
- European calendars: `session_calendar` now has XPAR, XAMS, XBRU, XLIS, XMIL, XDUB (euro-area superset), XETR, XFRA, XMAD (euro-area superset), XLON (England bank holidays incl. substitute days). Tests: `tests/test_eu_session_calendars.py`. **Calendars only**: stamping stays Oslo-only by default (`BIAP_EURONEXT_SESSION_DATE_MARKETS`), so no data changes until the owner enables more Euronext markets. Stockholm and Helsinki deliberately have NO calendar (existing guard test: SE/FI stay byte-for-byte unchanged until their holiday tables are verified). XLIS/XDUB local holidays are not in the superset; do not enable stamping for them without checking.
- Isolated EU jobs: runner + driver now versioned in `deploy/price-refresh/` (driver byte-identical to /usr/local). Runner adds a per-market status file and one retry for DEADLINE/NO_PROGRESS/NO_RESULT markets; dry-run with a stub driver passed (Milan DEADLINE then DONE, 11/11, exit 0). NOT installed in /usr/local (needs sudo + owner OK); production keeps the old runner until then.

## 2026-11-02 (P2.4 Global Top 10 diagnosis, no code change)
- `scan_global_top10` is a pure read path over per-market scan caches (max age 30 h). Read-only look at `/var/lib/biap-global/scan-cache` at 13:25 UTC: only DE (13:06) and NO (21:40 on 1 Nov) are inside the window; DK/ES/FI/FR/GB/IT/NL/SE caches date from 30 Oct, so "Partial global scan 1/9 markets ready" is stale caches, not a ranking bug.
- Fix is operational, in this order: (1) install the versioned runner from `deploy/price-refresh/` (needs sudo + owner OK), (2) let the scheduled EU refresh complete once, (3) re-check the Top 10 status. No production refresh was started by me.
- Still open in P2.4: sync-derived dates (1,273 records) and enabling Euronext stamping beyond Oslo (owner decision); SE/FI calendars unverified.
- ECB timer first run: 16:32:58 UTC; result check after 16:35 UTC.
