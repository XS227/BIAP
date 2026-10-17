# DE ledger corrections (C) + Rule B2: reviewable patch and activation conditions (2026-10-17)

Status: **patch prepared, disabled by default, not merged, not deployed. Frankfurt remains provisional.**

## What the patch adds
| File | Purpose |
|---|---|
| `analysis/global_markets/de_peer_policy.py` | strict rule, corrections (C), Rule B2; `apply_to_rows()` mutates rows in memory only |
| `analysis/global_markets/data/de_peer_evidence.json` | six reviewed issuers (printed figures, source URL, sha256, decision), copied from `docs/validation/DE_PEER_EVIDENCE_E6_2026-10-17.json` |
| `analysis/global_markets/evidence_store.py` | `rebuild_from_ledger` calls the policy for `DE` only when `BIAP_GLOBAL_DE_PEER_POLICY=1`; the applied log is returned as `dePeerPolicy` |
| `analysis/tests/test_de_peer_policy.py` | 8 tests (below) |

Safety: flag default OFF (behaviour identical to before). Ledger databases, fundamentals history, scan cache (except via the existing gated rebuild), DMA agents and research assets are never written by the policy. Rows already dated by a filing are untouched. Thresholds unchanged (15 % exclusion, 85 % P/E and P/B retention).

## Decisions encoded (evidence: `DE_OPTION_AB_COMPARISON_2026-10-17.md`)
* PZS revenue 10,000 -> 10,594.89 (stored value is the provider's 10,000 rounding step of the printed figure).
* DBAN net income 26.4m (Gesamtergebnis) -> 24.698m and EPS 1.40 -> 1.39; P/E rescaled at constant price.
* Z29 and RKB admitted by B2 (revenue 0.0, no revenue line in the income statement, NI matches, stored EPS reproduces to the cent from printed NI / shares).
* **Not changed:** VNA (revenue definition unconfirmed), BFV (printed EPS uses a different numerator).

## Tests (actual results)
* New + related DE tests: `test_de_peer_policy.py`, `test_de_option_ab_rules.py`, `test_de_peer_doc_verify_rounding.py` -> **22 passed**.
* Regression sweep `-k "evidence_store or benchmark or german or freshness or ledger"` -> **206 passed**, 0 failed.
* Covered: registry provenance, the six decisions, already-dated rows untouched, B2 negatives, parity with the evidence tool's rules, flag default off, hook is in memory / DE only / flag gated.
* Full test suite was not run.

## Remaining blockers and exact conditions for final activation
1. **Second-trading-day live verification, Monday 2026-10-19 (or later), after the Deutsche Börse delayed post-trade files for that date exist.** Same tool and method as the 2026-10-16 run (isolated copy, dry run, live quotes in memory only). Required: XETRA and FRANKFURT both `DRY_RUN_OK` under C + B2 with exclusion <= 15 %, P/E retention >= 85 %, P/B retention >= 85 % (Frankfurt needs >= 72 of 84 rows; the 2026-10-16 result was exactly 72/84, zero margin). If Frankfurt falls to 71/84 it stays REJECTED, no activation. Preferably also a one-row cushion (73/84).
2. **Owner sign-off on B2 admitting two thin shells.** Z29's quote had zero reported turnover (P/B 14.9, absorbed by the median); RKB EUR 489 turnover. Dropping either one fails Frankfurt. Alternatively a further verified issuer supplies the cushion.
3. **Baseline period-end evidence is not in production.** The 222 verified period ends (`DE_PEER_E5_OVERLAY_2026-10-16.json`) were applied only in the dry-run tool. This patch dates just the four admitted issuers. The gate results above assume that baseline state, so a separate approved step must persist those period ends (or equivalent) before the rebuild can reproduce them. I have not inspected the production ledgers in this session.
4. **Source re-check.** Confirm the six filings' sha256 values in `de_peer_evidence.json` are unchanged on the activation day (one reprice exclusion on 2026-10-16 was "filing may have changed").
5. **Operational:** merge approval; set `BIAP_GLOBAL_DE_PEER_POLICY=1` for the rebuild job; back up the DE scan caches; run the real (non-dry) `rebuild_from_ledger` for XETRA then FRANKFURT and read back `status`, `replaced` and `dePeerPolicy`; roll back by unsetting the flag.
6. **Known gaps:** VNA and BFV remain undated (no gate effect on Frankfurt; VNA is XETRA only). RKB ledger book value is about 7 % above the filing (does not change the result).
