# Overnight progress — 2026-10-13

Branch `feat/biap-global-overnight-20261013` (base `cc6e7d5`). Detail per market: `docs/market-audit/US_NASDAQ.md`, `docs/market-audit/GB_LSE.md`. Machine-readable state: `.overnight/checkpoint.json`.

## Milestones (all tested, pushed)
| Commit | Content |
|---|---|
| `0c73da2` | Ledger-based evidence totals (150-row payload cap was being read as the result), explicit `score × confidence` ranking basis, LSE preference-line rejection |
| `c417488` | SEC filing currency read from fact units (ASML files in EUR), independent BUY-candidate auditor |
| `b46ea80` | Reviewed Shell capex line (FCF), portfolio-profile isolation test, audit data |
| (this commit) | Cached LSE snapshot keeps genuine ordinaries 3IN/1SN/LWDB; test updated |

## Tests
Backend `pytest tests`: 1,028 passed. App `npm run test:api`: 14 passed. Old-vs-new regression on NO/SE/DE/GB/US: identical (`docs/market-audit/data/regression_*`). No thresholds or evidence gates were changed; no ranking was activated.

## Unresolved
* GB ranking BLOCKED: verified fundamentals 62.8 % < 70 %, genuine missing official filings (not a defect).
* US BUY list stale/unstable (needs refresh on fixed code; 45/55 not independently re-verified as raw cache evicted). Confidence is structural, not calibrated.
* EBITDA/FFO/ICR gaps are source-tagging limits (UK ESEF), not extraction bugs.

## Deployment / APK
NOT deployed: production still on `f15134a` (re-check with `curl -s 127.0.0.1:8091/health`). APK needs rebuilding after merge. No device test.

## Process status
No autonomous worker is running; nothing remaining is safe to run unattended (merge/deploy/ledger refresh need owner approval; timers were deliberately stopped in session 10). Disk is 95 % full (2.5 GB free) — watch before any refresh.

## Resume
`cd /home/ubuntu/biap-global/wt-overnight && git log --oneline -5 && cat .overnight/checkpoint.json`
