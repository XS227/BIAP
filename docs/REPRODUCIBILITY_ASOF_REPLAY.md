# Reproducibility of the stored v1 decision: as-of replay (for the paper's reproducibility section)

Written 2026-11-02. Script: `tools/asof_replay.py` (read-only: ledger copied, nothing written back, no network).
Data: `docs/asof_replay_results_IT_GB.json`, `docs/asof_replay_results_DK.json`.

## Problem
A plain replay on 2026-11-02 reproduced the stored v1 call **and** score for only IT 37/193, GB 394/816 (all rows, incl. out-of-scope), DK 17/116
(PHASE1_REPORT §2 note 1). Cause (investigated 2026-11-02): the replay re-evaluates **time-dependent inputs with today's clock**.
Quote age 0 d became 3–4 d (weekend), so `freshness_score` fell 1.0 → 0.65, `evidenceConfidence` 0.983 → 0.878 and the calibrated confidence
fell below the 0.55 accept threshold (e.g. RACE: HOLD_OR_WATCH → NO_RECOMMENDATION). The peer-benchmark age/cache was also read from today's
scan-cache instead of the cache that existed at analysis time. No provider change and no failed refresh was involved; the stored company inputs were identical apart from age/cache fields.

## Method: as-of replay
For every ledger row the clock is set to the row's `analyzed_at` (`datetime.now()` is frozen in every `global_markets` module) and the peer-benchmark
metadata / peer rows come from the stored record (`raw_provider_fields.peer_benchmark_freshness`, stored `sector_pe`), not from today's scan-cache.
Engine = v1, head `ed73661`. Comparison: stored `call` equal and `|score − stored score| < 5e-4`.

## Result (ledger vs as-of replay, all in-universe rows with a stored result)
| Market | Rows | Control: today's clock + today's cache (call+score) | Clock pinned only | **As-of (clock + benchmark pinned)** |
|---|---|---|---|---|
| IT Milan | 193 | 37 | 193 | **193/193 (100 %)** |
| GB LSE | 522 | 151 | 516 | **522/522 (100 %)** |
| DK Copenhagen | 116 | 17 (earlier run) | – | **116/116 (100 %)** |

Call-only agreement of the control run: IT 161/193, GB 474/522. The remaining GB gap with the clock pinned alone (6 rows) was closed by pinning the benchmark metadata.
(The GB control figure 151 differs from the earlier ad-hoc 139 because the ad-hoc count included 5 rows without a stored result; the script counts 522 rows with a result.)

## Paper-period snapshots (23 Oct – 1 Nov available; period runs to 19 Nov)
Daily snapshots store `analyzedAt` per row, but the ledger keeps **only the latest analysis**. A snapshot row can be replayed only if its `analyzedAt` equals the ledger's.

| Market | Snapshot row-days 23 Oct–1 Nov | Replayable | Snapshot conservative call = as-of replay | Not replayable (earlier analysis overwritten) |
|---|---|---|---|---|
| IT | 1930 | 760 (29 Oct: 181, 30 Oct–1 Nov: 193/day) | **760/760** | 1170 |
| GB | 5219 | 1566 (30 Oct–1 Nov: 522/day) | **1566/1566** | 3653 |
| DK | 0 (DK is not in the daily snapshots) | – | – | – |

## What this does and does not show (state it that way in the paper)
- The stored v1 decisions are **deterministic functions of the stored record plus the analysis timestamp**: replaying with that timestamp reproduces call and score exactly (3 markets, 831 rows).
- Earlier row-days (IT 23–28 Oct, GB 23–29 Oct) were produced by analyses whose inputs the ledger no longer holds; their snapshot values are the primary record and **cannot be re-derived**. They are not evidence of error, but they are not independently reproduced.
- A replay without the as-of clock is **not** a valid reproduction check; any figure that quotes replay fidelity must use `tools/asof_replay.py`.
- 2 Nov – 19 Nov is in the future: re-run the script on each new snapshot day (`--from 2026-10-23 --to 2026-11-19`) and append the result.
