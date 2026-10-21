# Investment-mode replay vs paper_dataset.xlsx (2026-10-21)

Read-only. No production data, services or the frozen snapshot were touched (snapshot copied to scratch, ledgers opened `mode=ro`).

## Inputs
| item | value |
|---|---|
| snapshot copy | 13/13 files OK against `MANIFEST.sha256`; `MANIFEST.sha256.json` sha256 `3ae6f35d32bedf66acb116d152ea5a48887cf6baaede08dd652fb0c478b56d0f` |
| paper_dataset.xlsx | sha256 `04500c62e41b63104fcb7c184da5b34a6818aa4da7b7adaa96ba8195d13a7545` (7,188 rows in `Stocks`) |
| code under test | `16e70a4b1da264c4fd9513cf035cfe066b294c2b` (detached worktree) |
| `buy_min_score` | 0.0 (confirmed, `investment_mode.py:94`); `INVESTMENT_MODE_MARKETS` = 12 venues (confirmed) |
| `pytest analysis/tests` | **1655 passed**, 0 failed (fresh venv: requirements.txt + pypdf + xlrd; the existing `analysis/.venv` lacks pypdf) |

## Replay
`replay_investment_mode.py`: all 12 ledgers -> `candidate_from_result` -> ONE `decide_market` call, default config.
7,590 candidates / 7,590 decisions. The xlsx has 7,188 rows because 402 Xetra/Frankfurt duplicates are merged by ISIN.
Compared by (listing, ticker): investment_tier, tier_before_flags, flags, peer_scope exact; score/confidence within 1e-6.

| variant | commit | matched / 7,188 |
|---|---|---|
| A. as specified (no sector reference) | 16e70a4 | **6,216** (972 mismatches) |
| B. + sector filled from ISIN `sector_reference_entries.json` where ledger sector is empty (xlsx `note=sector_reference`) | 16e70a4 | **6,384** (804 mismatches) |
| C. B on parent commit `28824fa` (before 771d567) | 28824fa | **7,188** (0 mismatches) |

## Mismatches
Full lists: `replay_mismatches_16e70a4_default.json` (A), `replay_mismatches_16e70a4_sector_reference.json` (B).

* A -> B: 168 rows differ only because the xlsx used the sector reference (fields inv_score, inv_confidence, peer_scope and flags/tier on those rows). The task text did not mention the reference; the xlsx note says it was used in replay.
* B (804 rows, 100%): a single cause. The xlsx has flag `distress_not_low_risk`; commit 16e70a4 emits `distress_unknown` for the same rows. 712 rows differ in `flags` only; 92 rows also differ in tier: xlsx `ACCUMULATE`, replay `BUY` (tier_before_flags differs too). No score, confidence or peer_scope mismatch remains in B.
* Cause: commit `771d567` (2026-10-19 20:45Z, "separates distress UNKNOWN from MEDIUM/HIGH") changed INSUFFICIENT_DATA/NOT_RUN/None distress to the info flag `distress_unknown` with no downgrade. The xlsx (file time 19:20Z) predates it. Variant C confirms: at `28824fa` all 7,188 rows match exactly.

## Conclusion
At 16e70a4 the xlsx does NOT replay exactly (6,384/7,188 with sector reference). It replays 7,188/7,188 on `28824fa`. Either regenerate the xlsx at the current code, or cite `28824fa` as the dataset's code version. Nothing was merged or deployed.
