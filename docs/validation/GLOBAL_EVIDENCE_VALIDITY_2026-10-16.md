# BIAP Global - evidence validity correction (2026-10-16)

Scope: PR #52. Nothing merged, deployed, deleted or restarted. All runs used the isolated copy `biap-validation-20261016/data-u9` (scan-cache copied, everything else symlinked, read-only); `/var/lib/biap-global` was not touched.

## 1. Audit: what is stored and why the engine stopped using it

| Evidence | Where | Expires? |
|---|---|---|
| Per-company analysis (validated compact result, `analyzed_at`) | `analysis-ledger/<CC>__<EX>.sqlite3` | never (immutable rows) |
| Fundamentals `latest.json` + `history/<period>.json`, ESEF/SEC packages | `fundamentals/`, `filings/` | never |
| Market snapshots / price history | `market/` | quotes age; history stays |
| Peer benchmark = `scan-cache/<CC>/<EX>.json` `payload.deepResults` | scan-cache | **was: 24 h from `cachedAt`** |

Root cause: `deepResults` is only `AnalysisLedger.summaries(limit=150)` - a copy of ledger evidence stamped with one `cachedAt`. The legacy rule judged the *copy's age*, so at +24 h the benchmark was "stale" while every underlying filing in the ledger/fundamentals was untouched. Decisions then failed closed (BUY -> WATCH) until a full re-scan re-wrote identical evidence.

## 2. Fixes (this branch)
* `freshness.py`: separate validity models - immutable filing (`classify_filing`: CURRENT / SUPERSEDED, always retained), benchmark input versions (fingerprints incl. per-row `inputsAsOf`), current quote (`quote_state`: CURRENT only within tolerance, else HISTORICAL, never relabelled), decision freshness (`decision_freshness`: BUY needs quote + benchmark + non-superseded filing [+ risk]).
* `evidence_store.py` (new): read-only (`mode=ro`) ledger reader, `inventory()`, `rebuild_from_ledger()` = benchmark reconstructed from stored evidence + one in-memory current-quote read (no bulk storage). Peers without a current quote are excluded, not repriced from old prices. Any failed gate leaves the cache untouched.
* `benchmark_refresh rebuild [--dry-run] CC:EX` CLI; `reprice` unchanged.
* `analysis_ledger.py`: opt-in `BIAP_GLOBAL_ANALYSIS_REFRESH_MODE=evidence` - re-analyse a row only when a newer filing can have been published since `analyzed_at` (default stays `age`).
* `service.py`: `price_state` exposed on every analysis.

## 3. Tests
`tests/test_evidence_store.py` (+47 targeted incl. freshness/ledger/benchmark) and full suite: **1550 passed**. Covers: ledger read leaves db bytes unchanged, superseded report retained but BUY-blocking, old price -> HISTORICAL not CURRENT, exclusion of rows without current quote, fail-closed on missing/forged evidence, refresh-mode semantics.

## 4. Before / after TTL expiry, per country (`tools/ttl_matrix.py`, data `GLOBAL_TTL_MATRIX_2026-10-16.json`)
Stored-evidence digest (file names/sizes of fundamentals, market, ledgers) before = after: **identical** (`ad0b3786b1dc43a5`).

| Market | Ledger rows | Rebuild | Peers kept | Usable now | +25 h (no refresh) | +7 d | BUY cands → pass gate | Stored evidence unchanged | Limiting reason |
|---|---|---|---|---|---|---|---|---|---|
| AE/ADX | 19 | REJECTED | 0 | False | False | False | 0 → 0 | True | only 0 rows repriced (< 50) |
| AE/DFM | 3 | REJECTED | 0 | False | False | False | 0 → 0 | True | only 0 rows repriced (< 50) |
| AU/ASX | 22 | REJECTED | 0 | False | False | False | 0 → 0 | True | only 0 rows repriced (< 50) |
| BE/EURONEXT_BRUSSELS | 102 | OK | 68 | True | True | False | 3 → 3 | True |  |
| BR/B3 | 150 | REJECTED | 4 | False | False | False | 0 → 0 | True | only 4 rows repriced (< 50) |
| CA/TSX | 44 | REJECTED | 0 | False | False | False | 1 → 0 | True | only 0 rows repriced (< 50) |
| CA/TSXV | 28 | REJECTED | 0 | False | False | False | 0 → 0 | True | only 0 rows repriced (< 50) |
| CH/SIX | 25 | REJECTED | 0 | False | False | False | 0 → 0 | True | only 0 rows repriced (< 50) |
| DE/FRANKFURT | 150 | REJECTED | None | False | False | False | 1 → 0 | True | fundamentals not valid for repricing: 74% of peers excluded  |
| DE/XETRA | 150 | REJECTED | None | False | False | False | 0 → 0 | True | fundamentals not valid for repricing: 79% of peers excluded  |
| DK/NASDAQ_COPENHAGEN | 116 | OK | 74 | True | True | False | 3 → 3 | True |  |
| ES/BME_MADRID | 106 | OK | 73 | True | True | False | 1 → 0 | True |  |
| FI/NASDAQ_HELSINKI | 146 | OK | 95 | True | True | False | 4 → 4 | True |  |
| FR/EURONEXT_PARIS | 150 | OK | 124 | True | True | False | 3 → 2 | True |  |
| GB/LSE | 150 | OK | 132 | True | True | False | 17 → 15 | True |  |
| GR/ATHENS | 46 | REJECTED | 0 | False | False | False | 0 → 0 | True | only 0 rows repriced (< 50) |
| HK/HKEX | 34 | REJECTED | 0 | False | False | False | 0 → 0 | True | only 0 rows repriced (< 50) |
| IE/EURONEXT_DUBLIN | 16 | REJECTED | 12 | False | False | False | 0 → 0 | True | only 12 rows repriced (< 50) |
| IN/BSE | None | REJECTED | None | False | False | False | 1 → 0 | True | no stored ledger evidence for this market |
| IN/NSE | 39 | REJECTED | 0 | False | False | False | 1 → 0 | True | only 0 rows repriced (< 50) |
| IS/NASDAQ_ICELAND | 27 | REJECTED | 12 | False | False | False | 0 → 0 | True | only 12 rows repriced (< 50) |
| IT/EURONEXT_MILAN | 150 | OK | 142 | True | True | False | 5 → 5 | True |  |
| JP/TSE_JP | 24 | REJECTED | 0 | False | False | False | 0 → 0 | True | only 0 rows repriced (< 50) |
| KR/KRX | None | REJECTED | None | False | False | False | 0 → 0 | True | no stored ledger evidence for this market |
| NL/EURONEXT_AMSTERDAM | 98 | OK | 58 | True | True | False | 3 → 3 | True |  |
| NO/EURONEXT_OSLO | 146 | OK | 94 | True | True | False | 10 → 10 | True |  |
| NZ/NZX | 18 | REJECTED | None | False | False | False | 0 → 0 | True | fundamentals not valid for repricing: 15% of peers excluded  |
| PT/EURONEXT_LISBON | 30 | REJECTED | 26 | False | False | False | 0 → 0 | True | only 26 rows repriced (< 50) |
| SA/SAUDI_EXCHANGE | 21 | REJECTED | 0 | False | False | False | 0 → 0 | True | only 0 rows repriced (< 50) |
| SE/NASDAQ_STOCKHOLM | 150 | OK | 144 | True | True | False | 1 → 1 | True |  |
| SG/SGX | 34 | REJECTED | 0 | False | False | False | 1 → 0 | True | only 0 rows repriced (< 50) |
| TR/BIST | 150 | REJECTED | 17 | False | False | False | 0 → 0 | True | only 17 rows repriced (< 50) |
| US/NASDAQ | 150 | OK | 143 | True | True | False | 19 → 17 | True |  |
| US/NYSE | 150 | OK | 139 | True | True | False | 18 → 15 | True |  |
| ZA/JSE | 17 | REJECTED | None | False | False | False | 0 → 0 | True | fundamentals not valid for repricing: 27% of peers excluded  |

### Reading the table
* **11 markets (BE, DK, ES, FI, FR, GB, IT, NL, NO, SE, US x2)** rebuild from stored evidence, stay usable at +25 h with no refresh (the old cliff is gone) and return to unusable by +7 d until a quote reprice - by design (4-day quote tolerance, 336 h ceiling).
* BUY gate: e.g. GB 17 -> 15, US NASDAQ 19 -> 17, ES 1 -> 0, FR 3 -> 2 - candidates lacking a current quote/valid filing are blocked, none relabelled.
* **Rejected, fail closed (no benchmark, no BUY):** DE (74-79% of peers may have newer filings: needs source refresh), NZ, ZA (same reason, smaller share); AE, AU, BR, CA, CH, GR, HK, IE, IS, JP, PT, SA, SG, TR, IN-NSE - ledger holds only 12-26 analysed rows (< 50 minimum) and/or the Twelve Data quote batch returned no rows; IN-BSE, KR - no ledger. These were not working before either; they need analysis coverage, not a TTL change.

## 5. Open items / needs approval
Merge #52, deploy, one `rebuild`/`reprice` run for the 11 markets, timers - none done. Risk-signal gate decision and a source-update feed producer remain open. DE needs a targeted peer rebuild.
