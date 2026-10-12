**BIAP Global v0.3.21 — progress (2026-10-12), branch `feat/biap-global` — NOT release-complete; real Android testing PENDING. Not merged to main.**

Commits audited and present on prod: `58792dc`, `ddcfd41`, `9cd575e`, `52d7bcc`, `5b49fad`. New: `b883fcc` (+ docs commit).

**Fixed in b883fcc**
- Portfolio held one issuer twice (ASML NASDAQ 16.9% + Amsterdam 3.1%, GOOGL+GOOG) → second listing now rejected `duplicate_issuer` (validated LEI/CIK identity; unrelated issuers never merged).
- NXT market cap 2.5x too low (stale 2023 SEC share count) → stale/inconsistent share counts withheld; market cap/P-B/EV-EBITDA empty rather than wrong.

**Tests**: backend 967 passed; client API tests 8 passed; `tsc` clean; staging smoke OK; prod smoke after deploy OK (ASML once, GOOGL once, NXT cap withheld). 29-listing prod sweep (TSLA, SHEL, ASML, NXT, US/GB/FR/IT/SE/NO): no P/E, ICR or EBITDA inconsistency.
**Deployment**: prod commit `b883fcc9e34de5f8555539eb35e6e88bf40750ef`; rollback `git checkout 5b49fad` + `deploy/restart-global-prod.sh`.
**APK**: 0.3.21 (versionCode 24), CI run 38209921947 from b883fcc, `https://biap.dadashi.no/global/download/BIAP-Global-latest.apk` HTTP 200, sha256 `70e6faee280d13a56b85c040c0c98d33dbe047543af87606b11f03eebaf5d920`.
**Verdicts**: US PASS, SE PASS; GB/FR/IT/NO WARN (sector empty, P/E withheld for foreign-currency reporters, SHEL EBITDA not verifiable); DE excluded (BLOCK).
**Blockers**: device test PENDING; interactive scans can 504 at nginx 120 s under load; sector gaps. Details: `docs/audits/global-fixes-2026-10-12-session7.md`.
