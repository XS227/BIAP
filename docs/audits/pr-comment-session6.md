**BIAP Global v0.3.19 — status (2026-10-12), branch `feat/biap-global`** — not merged, release NOT complete.

Commits: `ddcfd41`, `9cd575e` (+ docs). Details: `docs/audits/global-fixes-2026-10-12-session6.md`.

**Fixed**
- Duplicate issuer in Global Top 10 (ASML NL + NASDAQ): name normalization (`N.V.`/registry shares), CIK↔LEI bridge with unique-match rule + verified ASML map; applied to rankings and portfolio issuer cap; secondary listings stay in `otherSecurities` and search. Staging: 10/10 unique issuers; portfolio holds ASML once.
- Freshness: app now shows source verification, fundamental period tier/date, and price date separately (TSLA/TSLX/SHEL = LAST_ANNUAL_FILING, period 2025-12-31, 285 d; price 3 d).
- Shell: re-audited; EBITDA/operating income/FCF not verifiably tagged → left empty, Agent 9 INSUFFICIENT_DATA, Agent 10 no rating.

**Tests**: backend 961 passed; client logic 8 passed; `tsc` clean; `expo lint` has 18 pre-existing errors (untouched code). Staging sequential API checks: GB/LSE scan 20.6 s, 1.33 MB → 140 KB gzip, RSS 141 MB; Top 10 and portfolio OK.

**Unresolved**: no on-device test done; no APK built/published; prod not restarted (owner-run `deploy/restart-global-prod.sh`); Shell interim data not ingested; cross-listing bridge relies on exact normalized names for pairs beyond ASML.

**Still required**: real-device Android validation, APK build from latest commit, prod deploy, then re-review before any merge.
