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
