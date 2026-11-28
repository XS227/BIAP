# Global: enable Decision Accuracy, Risk and Performance (2026-11-28; owner approved Steps A-D, E "My holdings" skipped)

Not executed from the cloud session: it has no access to the production server. Run on the server as `ubuntu`.

## Step A: registered rerun (done, PR #129)
Exit 2026-11-20, seed 20261020, 10,000 resamples, registered script `5f60385` (sha256 8314...4668), frozen snapshot (sha256 0bd9...21a1) only read.
Output and SHA-256 list: `research/outputs/20261120_registered/` (`SHA256SUMS.txt`). Offline replay on 2026-11-28 reproduced
`returns_2026-11-20.json`, `per_holding.csv`, `summary.json`, `run_log.txt` byte for byte. A fresh Yahoo pull was not possible from the cloud session.
Venue-equal BUY -2.28%, SELL +6.61%, spread -8.89 pp, 95% CI -49.69 to +12.85 pp (427 BUY, 487 SELL, 957 of 964 priced).
One UK holding (GVMH) has a x100 vendor price error; without it the spread is +10.78 pp. Showing these figures in the app is PR #130 (draft, owner decision).

## Steps B-D: one command each, automatic rollback
Prerequisite: release the commit with this file (`sudo deploy/restart-global-prod.sh <commit>`). Then, outside 22:45-02:00 UTC and the refresh windows:
```
deploy/enable-global-agent.sh accuracy      # Step B
deploy/enable-global-agent.sh risk          # Step C (D2 levels = calibration proposal D, already in config version 5)
deploy/enable-global-agent.sh performance   # Step D (R7 guard in this release)
# or all three in order, stopping at the first failure:  deploy/enable-global-agent.sh all
```
Each run backs up `.env.global`, adds one flag, restarts, and runs checks a-g. On any FAIL it removes the flag, restarts and confirms the route answers 404,
then stops and names the failing check. Log: `/tmp/enable-global-agent-<time>.log`.

| Check | accuracy | risk / performance |
|---|---|---|
| a | `/global/status`: this flag and the earlier ones on, later ones off | same |
| b | summary h=1: 200 in < 3 s; BUY -0.35, SELL -10.93, spread 10.57, 12 markets (override with `EXPECT_ACCURACY` if #130 is released) | US AAPL, DE SAP, IT ENI, KR 005930: 200 in < 1 s; "data not yet available" never has a level; Risk: version 2 and calibration field (not_calibrated outside US); Performance: `statementDefects` field present |
| c | h=3 says "not matured" | JP 5243 answers 422 |
| d | decisions 200, stock 200/404 | - |
| e | Risk and Performance 404 | Iran 404; later agents 404 |
| f | `/global/analyze` AAPL 200 | same |
| g | journal since restart: no traceback, no 5xx | same |

Rollback by hand (under one minute): `deploy/enable-global-agent.sh --rollback accuracy|risk|performance`
(or `sed -i '/^<FLAG>=/d' analysis/.env.global && sudo systemctl restart biap-global.service`; backups are `analysis/.env.global.bak-<time>-<agent>`).
Code rollback of the R7 guard: revert its merge commit, then `sudo deploy/restart-global-prod.sh <commit>`.

After each step: repeat `journalctl -u biap-global --since -30min` after 30 minutes and the next morning. The plan of one flag per day is overridden by the owner's instruction of 2026-11-28.

## R7 (Performance impossible-value guard)
`performance_agent.statement_defects`: total assets <= 0, revenue < 0, |net income| > 5x total assets give no level (status INSUFFICIENT_DATA,
`statementDefects` lists the reasons). QA report counted 37 stocks with revenue < 0 and 61 with |NI| > 5x assets on the staging copy.
