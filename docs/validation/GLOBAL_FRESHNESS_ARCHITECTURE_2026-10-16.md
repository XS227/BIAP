# BIAP Global freshness architecture - root cause, design, migration safety, test results (2026-10-16)

Scope: PR #52 (`feat/global-evidence-signals`). Nothing was merged, deployed, restarted or scheduled. No timer or systemd unit was added.

## 1. Root cause of the repeating 24-hour expiry

`_scan_peer_state` judged the peer benchmark with one wall-clock rule, `cachedAt <= 24 h`. That single number stood in for five different things with five different lifetimes:

| What it really is | Real lifetime | Old treatment |
|---|---|---|
| Peer **filings** (EPS, EBITDA, book) | until a newer filing can exist (weeks to months) | 24 h |
| Peer **universe** (which tickers/ISINs) | until the official directory changes | 24 h |
| **Benchmark calculation** (medians) | a pure function of the inputs above + method version | 24 h |
| Peer **quotes** | trading days | 24 h |
| **Risk signals** (volatility, drawdown) | trading days | not modelled |

Consequence: unchanged filings and an unchanged universe expired daily; the only cure was a full re-scan of the market (the thing we must not run in bulk). Only DE had a timer, so the other six markets (US/GB/FR/IT/SE/NO) all hit the cliff together (2026-10-16 ~21:42-21:46Z). The failure mode was safe (BUY fails closed) but it recurs forever and cannot be fixed by "extending the TTL", which would relabel stale evidence as fresh.

## 2. Architecture (implemented, `analysis/global_markets/freshness.py`)

Five independent dimensions; only quotes and risk signals are time-based.

| Dimension | Valid while | Invalidated by | Renewed by |
|---|---|---|---|
| **Filing validity** (per peer) | no filing can have been *published since the base scan* per the country reporting calendar (cadence/lag table), and none is named by the optional source-update feed `source-index/peer-invalidations.json` | a publication window opens after the base; a source update names a newer period; undated filing | targeted rebuild of the listed peers (not implemented, see section 6) |
| **Peer universe** | `(ticker, ISIN)` set fingerprint equals the validated one | any membership change | rebuild |
| **Benchmark calculation** | calc fingerprint = hash(universe fp, fundamentals fp, quote date, `METHOD_VERSION`) still matches | edited rows, new method version (bump forces recompute everywhere), tampered block | recompute from validated inputs |
| **Quote freshness** | peer quote date within 4 calendar days (`BIAP_GLOBAL_PEER_QUOTE_TOLERANCE_DAYS`) | time | **online reprice**: one official exchange-wide quote read held in memory, rows rescaled, one JSON replaced in place |
| **Risk-signal freshness** (target) | price history <= 5 days | time | normal online enrichment |

Rules that make it fail closed and un-fakeable:

* Never extends `cachedAt`. Freshness lives in an explicit `benchmark` block (schema 2) with versioned fingerprints; a block whose status, method version, base timestamp or any fingerprint does not match is ignored (tests forge five variants).
* A peer whose fundamentals may have been superseded or cannot be dated is **excluded from the medians**, never carried with a "fresh" label. Exclusions may not exceed 15 % of the benchmark members; rows that never had a P/E or P/B are non-members and do not count. Above the budget the benchmark is STALE and `_critical_data_gaps` blocks BUY ("valuation benchmark unavailable").
* Price-dependent multiples are rescaled (P/E, P/B, market cap x price ratio; EV/EBITDA keeps net debt constant; yield / ratio), only after gates: coverage >= 85 %, P/E and P/B retention >= 85 %, >= 50 rows, median market move within 0.8-1.25, >= 90 % of quotes dated within tolerance, per-row ratio within 0.5-2.0 (splits/feed errors are excluded). Any failed gate leaves the file byte-identical.
* Repricing always restarts from the pristine full scan (`<market>.json.base`), so it is idempotent, has no cumulative drift, and transient exclusions (e.g. a missing quote) recover.
* Hard backstop: a base older than 336 h (`BIAP_GLOBAL_PEER_BASE_MAX_HOURS`) is STALE until a source-update feed exists.
* Legacy caches (no block) keep the old 24 h rule unchanged, so deployment alone changes no decision. Every new full-scan writer (`scan_service._write_scan_cache`, `refresh_benchmark`) stamps the block.
* Official Euronext/Nasdaq-Nordic snapshots carry no per-row quote date; their quotes are dated with the retrieval date and recorded as `quoteDateBasis: retrieved_at` (never as a source date).
* The ranking, recommendations and `cachedAt` of the scan are **not** refreshed by a reprice; Global Top continues to follow its own rules.

Applies to every enabled country pack through the same code path (no per-country branches except the reporting-calendar table; unknown countries get the conservative semi-annual regime). Policy parameters (cadence/lag table, 15 % budget, 4-day quote tolerance, 336 h ceiling) are owner-tunable constants.

## 3. Recurring operation without permanent bulk storage

`python -m global_markets.benchmark_refresh reprice [--dry-run] [--workers N<=2] CC:EXCHANGE ...`

* one exchange-wide official quote read per market (in memory), peers already in the validated cache only (<= 200 rows), sequential by default, `flock` per market, `nice 10`, address-space cap (`BIAP_BENCH_MAX_MB`, default 1536), stale `*.tmp` cleanup, exit code reflects success;
* storage: one existing JSON per market replaced atomically, plus `.prev` (one generation) and `.base` (+ `.base.prev`) of ~0.75 MB each; no per-company files; online-first mode stays on;
* measured on 7 caches (US x2, GB, FR, IT, SE, NO): **28.7 s wall, 84 MB peak RSS**.

A timer is only a scheduler for that command (e.g. daily on trading days); it is **not installed** and needs explicit approval. Because quote tolerance is 4 days, a missed run no longer causes an immediate cliff.

## 4. Migration safety

* No data is deleted or rewritten in production by this change. Production `scan-cache/**` fingerprint (sha256 over all files) before and after this work: identical (`9084fa11...cea1a0`). Port 8091 service untouched (still started 2026-10-16 00:10).
* All live tests ran on an isolated copy (`.../biap-validation-20261016/data-u9`, 961 MB, excludes `cache/esef`, `sec-edgar*`, backups, history). ESEF archives, DMA agents and `backup-*` snapshots untouched.
* Rollback: `git revert`; caches written by reprice are readable by the old code (extra keys ignored; `cachedAt` unchanged so old code simply sees them as ageing normally); `.prev` / `.base` hold the earlier files.
* First deploy changes no decision (legacy rule until a v2 block exists). Merging PR #52 triggers deploy-backend (`analysis/**`), so merge/deploy remain subject to approval.

## 5. Test results

* Full suite on this branch: **1503 passed** (1442 at Update 7; +61 new tests in `tests/test_freshness_model.py`, `tests/test_benchmark_reprice.py`).
* New tests cover: expiry (no 24 h cliff when inputs unchanged; quote-only staleness renewed by reprice; 336 h backstop), source updates (feed exclusion within/over budget; calendar-based detection; per-country regimes), missing data (no cache, undated filings, empty/legacy, risk inputs), tampering (five forged blocks), method-version bump, fingerprint edits, idempotent restart from base, bounded rows, dry run, locking, worker cap, and **decision stability for every enabled market** (one parametrised test per market, 40 markets: same semantics, identical P/E median at unchanged prices, exact x1.05 scaling, identical fail-closed result when damaged).
* Real-data regression, BHP / HAUTO / WWI (isolated copy, caches aged to 24.5 h to reproduce the expiry; same base date as the real 21:4xZ expiry):

| Stage | BHP (GB) | HAUTO (NO) | WWI (NO) |
|---|---|---|---|
| 1. Before expiry (fresh) | BUY, conf 0.667532 | BUY, 0.62817 | BUY, 0.575781 |
| 2. After expiry, no refresh | NO_RECOMMENDATION / WATCH (fail closed) | HOLD_OR_WATCH / WATCH | NO_RECOMMENDATION / WATCH |
| 3. After validated online reprice | BUY, 0.667532 | BUY, 0.62817 | BUY, 0.575781 |

  Stage 1 and 3 are identical to Update 8 (decision stability); stage 2 is the intended fail-closed behaviour (cause `GOVERNANCE_RESTRICTION`, draft confidence lower because the comparison agent has no benchmark).
* Live reprice of 7 caches (rows / repriced / excluded): US NASDAQ 150/143/7, US NYSE 150/139/11, GB 150/132/18 (17 peers with Jan/Feb year-ends excluded because an interim filing may have been published), FR 150/124/26, IT 150/142/8, SE 150/144/6, NO 146/94/52 (51 never had P/E or P/B). Coverage 88.6 %-100 %, median price ratio 0.988-1.016, all quotes dated 2026-10-16.
* Bug found and fixed by the real-data run (not by unit tests): a first version counted rows that never had a multiple against the exclusion budget, which wrongly made Norway STALE (36 %); and a first "overdue filing" rule would have blocked every market because peer rows are annual-based by design. Both are now covered by tests (`test_rows_that_never_fed_a_median...`, `test_filing_changes_are_detected_from_the_country_reporting_calendar`).

## 6. Unresolved blockers / limits (honest list)

1. **Filing validity is calendar-inferred, not observed.** The optional `peer-invalidations.json` feed does not exist yet; until a source-aware producer writes it (e.g. from SEC/OAM/Euronext filing indexes), the 336 h ceiling is the backstop. Cadence/lag table values are policy and need owner review.
2. **Targeted peer rebuild is not implemented.** Excluded peers are listed (`filingDimension.excluded`) but re-analysing just those rows is a separate bounded job. Without it, a benchmark degrades as earnings season excludes more peers (> 15 % => STALE => fail closed). Recommended next step.
3. **Risk-signal dimension is reported, not yet a gate.** `risk_signal_dimension` exists and is tested; wiring it as a critical gap could flip live BUYs and needs a decision.
4. **Real 21:4xZ expiry not yet observed live.** The expiry was reproduced by aging an isolated copy; a read-only re-check of production after 21:46Z is recommended (`docs/validation/tools/regress10.py`, no writes).
5. Production caches carry no v2 block until the first reprice/full scan after deploy; today's six markets will still expire at 21:4xZ (old rule) unless the owner approves a deploy + one reprice run or a one-off manual run.
6. Markets with very low filing-date coverage (AE, KR, parts of CA/HK/JP/IN/SA/SG/ZA) are UNDETERMINED and fail closed by design; they were not part of the live reprice.

## 7. Recommended next steps (all need approval)

1. Approve merge of #52 + a deploy window; run `reprice` once for the six markets (about 30 s) and verify BHP/HAUTO/WWI with `docs/validation/tools/regress10.py`.
2. Approve a daily-on-trading-days timer calling `reprice` (not installed; draft unit can be supplied).
3. Build the source-update producer and the bounded targeted-rebuild job (section 6.1-6.2).
4. Decide whether the risk-signal dimension becomes a BUY gate.
