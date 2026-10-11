# Checkpoint 2026-10-11: NZX Ltd / Summerset PDF parsing fixes (scope: those two only)

## Root causes (confirmed on the live announcement PDFs, FY2025)
1. NZX Ltd p124 auditor's report: pypdf *layout* mode returns '' for the page (rotated text matrix). `read_pdf_pages` now falls back to plain extraction only when layout text is empty.
2. Both: balance sheet closes with "Total equity attributable to shareholders" -> label added to the tier-0 total_equity labels (assets = liabilities + equity tie still enforced; conflicting equity rows still rejected as ambiguous).
3. NZX: income row "Operating revenue  8/9  128,948 ..." — multi-note reference "8/9" was a label chunk that swallowed the values -> treated as a note cell.
4. Summerset: "Profit  for the period" printed with a double space was split into two chunks, so net income was never matched -> a 2-space gap between non-numeric chunks (next starts lowercase) is re-joined. Failure mode of a wrong join is a missing field (reject), never a moved value.
No acceptance rule was loosened: period, scale, currency, balance tie, ambiguity and audit-opinion checks unchanged.

## Results
- Extractor: NZX OK (rev 128,948k, NI 21,475k, equity 122,185k, audit p124); SUM OK (rev 361,774k, NI 259,720k, equity 3,327,862k, audit p91).
- Live provider cross-check (legacy parser vs extractor): NZX verified, SUM verified.
- Tests: tests/test_global_nzx_pdf_regressions.py (7; 3 use the real PDFs in ~/biap-global/pdf-real, skipped if absent; fail 7/7 without the fix). Full analysis suite: 874 passed.

## Remaining blockers
- SCL legacy parser fails at baseline (not touched). FPH annual-report announcement not located by the locator.
- Venv for tests: ~/biap-global/venv-pdf (system python lacks pypdf).
- Push touches analysis/global_markets/** -> CD auto-deploys prod; re-run any live-check workflow that started during the restart.

## Final verification (2026-10-11, no new development)
- `test_global_nzx_pdf_regressions.py` at b59a451: 7 passed, 0 failed, 0 skipped (venv-pdf).
- Working tree clean; HEAD == origin/feat/biap-global == b59a451; main synced (5104606).
- CI on b59a451: Global check, Sync main, Setup BIAP Global server (prod deploy), both live checks all success.
- Prod service biap-global active on :8091.
