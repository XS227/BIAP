# Germany (DE) peer rebuild – verification report (2026-10-16)

Base: `4f75361` on `feat/global-evidence-signals` (PR #52). Docs-only change. Nothing merged, deployed, deleted or restarted.

## Safety / method
- Preflight: disk 7.0 GB free (86 %), swap 2.0/2.0 GB full, repo clean. Batches kept small; no bulk download.
- Production data and ledgers were **read-only**. The rebuild was a `dry_run` on an isolated 11 MB copy of the DE ledgers + scan-cache (scratchpad, not committed). Quotes: offline fixture (stored price) — only the filing-validity gate was under test, so no network and no new data was stored.
- No DMA agents / unrelated projects touched.

## Result: DE rebuild FAILS CLOSED (REJECTED) on both markets
| Market | Peer rows | Dated | Undated (`filing_undated`) | Excluded | Gate (≤15 %) | Status |
|---|---|---|---|---|---|---|
| XETRA | 150 | 40 | 105 (+7 no EPS) | 78.9 % | FAIL | REJECTED |
| FRANKFURT | 150 | 55 | 85 (+10 no EPS) | 73.9 % | FAIL | REJECTED |

Existing DE benchmark/cache left untouched. This reproduces (and quantifies) the s43 finding.

## Companies examined (ledger, in_universe)
XETRA 406, FRANKFURT 498 = **904**.

| Category | XETRA | FRANKFURT |
|---|---|---|
| Rebuildable from stored evidence (price, EPS, sector, net income, period end all present) | 27 | 20 |
| Börse Frankfurt key data, **year-only** period (exact period end not supplied by endpoint) | 118 | 107 |
| Missing sector **and** period end (mostly Open Market/Scale – no ESEF obligation) | 218 | 288 |
| Missing sector only | 14 | 22 |
| Missing EPS (± other) | 12 | 18 |
| BLOCKED | 11 | 28 |
| INSUFFICIENT_DATA | 6 | 14 |

**Successful peer rebuilds: 0 markets** (47 individual rows are fully rebuildable: 27 + 20; far below the 50-row minimum and 85 % retention gates).

## Remaining BLOCK reasons
1. `filing_period_end` absent for ~79 %/74 % of peers: Börse Frankfurt `historical_key_data` is year-granular (`de_bf_exact_period_end_available=false`); Scale/Open-Market issuers publish no ESEF report. Inventing a period end would violate the evidence rules, so it was **not** done.
2. `sector` absent for most undated rows.
3. Missing EPS / net income for a handful of rows.

## Decisions (stored)
Complete rows — XETRA: 4 HOLD_OR_WATCH, 1 AVOID_OR_REVIEW, 384 NO_RECOMMENDATION; FRANKFURT: 1 BUY_CANDIDATE, 3 HOLD_OR_WATCH, 1 AVOID_OR_REVIEW, 451 NO_RECOMMENDATION. The single BUY_CANDIDATE is **not** actionable: DE benchmark is invalid, so BUY stays gated (restricted GO excludes DE). No SELL.

## Options needing owner decision (not done)
- A. Policy: accept year-only periods using the *earliest* plausible bound (conservative) for the freshness gate; exact dates only where ESEF exists. Needs gate-code change + approval.
- B. Targeted online fetch (in-memory) of exact period ends/sector for the ~105+85 undated peers in batches of ≤10 (e.g. Unternehmensregister/ESEF); sizeable network work, acceptable if approved.
- C. Keep DE excluded from the GO set (current state).

## Per-country status (unchanged from s43, 9a6c755/4f75361)
US, GB, FR, IT, SE, NO: restricted GO (ledger rebuild usable, 0 new BUY without fresh quotes). DE: NO-GO / fail closed.

## Tests
No source code changed in this step. Gate behaviour verified by the dry-run above (2/2 DE markets REJECTED as designed). Full suite not re-run (no code delta; last: 1550 PASS on 9a6c755).
