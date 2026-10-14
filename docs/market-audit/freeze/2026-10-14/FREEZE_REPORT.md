# BIAP Global research freeze assessment — 2026-10-14

**Decision: NO-GO for a paper-grade, all-market dataset.** Conditional GO only for a restricted, clearly labelled
sub-sample (see "What can be frozen now"). The pipeline itself is stable and validated; the blockers are source-data
completeness and two un-run validations (device test, post-deploy production comparison).

## 1. Reproducibility
- Code commit: see `FREEZE_MANIFEST.json` (`gitCommit`); tests: 1,088 passed / 0 failed (clean env, `pytest tests`).
- Agent regression on the tested commit (temporary instance, isolated data dir): 101 cases over all 34 ledger markets,
  six scoring agents + Agents 8/9/10, 0 invariant errors (`docs/market-audit/data/agent_regression_2026-10-14_7a49767.json`).
- Scoring configuration (unchanged; no threshold was relaxed in this program): confidence-weighted mean of six agent votes;
  BUY needs score >= 0.25, confidence >= 0.45, evidence PASS, no Agent 9 positive block; Agent 8 accept >= 0.55, escalate 0.35-0.55, abstain < 0.35.
- Hashes of the scoring code, registries and all 34 ledgers: `FREEZE_MANIFEST.json`. Ledger backup: `/var/lib/biap-global/backup-s25-predeploy-20261014T071722Z` (SHA256SUMS).

## 2. Coverage and field completeness (analysed rows, % with value; `COVERAGE.json`)
| Market | Universe | Analysed | revenue | op. income | EBITDA | assets | debt | op. CF | FCF | interest | P/E | P/B | EV/EBITDA | sector | period |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| DE Xetra | 406 | 389 | 98.5 | 93.8 | 2.3 | 99.5 | 6.7 | 8.2 | 6.4 | 3.3 | 63.5 | 87.7 | 0.0 | 30.3 | 10.5 |
| DE Frankfurt | 498 | 456 | 97.8 | 94.1 | 2.9 | 99.6 | 6.8 | 8.6 | 6.8 | 3.1 | 63.2 | 86.4 | 0.0 | 29.2 | 10.5 |
| SE Stockholm | 402 | 373 | 83.6 | 89.3 | 38.6 | 100.0 | 54.7 | 96.5 | 68.4 | 90.1 | 63.0 | 13.1 | 4.8 | 100.0 | 100.0 |
| NO Oslo | 146 | 136 | 97.1 | 94.1 | 72.1 | 100.0 | 64.0 | 94.1 | 57.4 | 86.0 | 43.4 | 2.2 | 1.5 | 100.0 | 100.0 |
| GB LSE | 527 | 420 | 89.5 | 87.1 | 44.8 | 91.7 | 64.3 | 98.3 | 76.7 | 90.2 | 52.6 | 0.2 | 0.0 | 90.5 | 100.0 |
| IT Milan | 193 | 169 | 96.4 | 81.1 | 63.9 | 99.4 | 30.2 | 94.1 | 58.0 | 74.0 | 59.8 | 1.2 | 0.0 | 100.0 | 100.0 |
| US Nasdaq | 3,010 | 2,807 | 82.7 | 84.8 | 75.5 | 99.8 | 43.7 | 98.0 | 69.3 | 55.2 | 37.3 | 67.3 | 24.4 | 94.7 | 100.0 |
| US NYSE | 1,798 | 1,602 | 92.3 | 74.5 | 65.8 | 99.9 | 70.0 | 97.5 | 56.8 | 68.7 | 69.7 | 58.1 | 36.1 | 91.0 | 100.0 |
Ledger rows keep the values from their last analysis: the DE sector (30%) and period (10.5%) figures predate the Deutsche
Boerse sector reference (82% coverage at universe level) and the four reviewed DAX statements; they update on re-analysis.

## 3. Material validation gaps (why NO-GO)
1. **Germany:** EBITDA, debt and cash-flow inputs exist for <10% of analysed rows (only DAX names sourced this session plus the
   reviewed registry). Agent 9/10 and the fundamental/quality agents therefore abstain or run on partial inputs for ~90% of DE.
2. **P/B and EV/EBITDA:** need an official shares-outstanding source; absent for DE, GB, IT, NO, SE (P/B 0.2-13%, EV/EBITDA <5%).
3. **Cross-currency reporters** (GB 114, NO 41, SE 33 rows): per-share valuation ratios are suppressed, no FX conversion exists.
4. **Comparison agent** depends on a <= 24 h peer-P/E scan cache; 0% active for DE in stored ledgers.
5. **Device validation of APK 0.3.22 is pending** (no device available; nothing claimed).
6. **Production still serves 46fc92e**; the tested commit needs the owner-run `deploy/restart-global-prod.sh` (sudo) and a post-restart
   `/health` comparison before the frozen results can be called production-equivalent.
7. Rheinmetall: official FY2025 balance sheet could not be retrieved; remains INSUFFICIENT_DATA.

## 4. What can be frozen now (restricted sample)
Markets whose core inputs are >= 85% complete and whose statements are official: **US Nasdaq/NYSE (fundamental inputs), NO, SE, GB
(income-statement and cash-flow based agents)**, with P/B and EV/EBITDA excluded from analyses. Document the exclusion list and
the abstention rates per agent (`agentActivePct` in `COVERAGE.json`) in the paper; do not present Germany as comparable.

## 5. Ablation readiness
Each agent's vote/confidence is stored per company in the ledger (`signals`), so drop-one-agent ablations can be recomputed from
ledgers without network access. Comparison-agent ablations should use rows analysed with a fresh peer cache only.

## 6. Next actions to reach GO
1. Owner runs the restart script on the final commit; verify `/health` commit equals the tested commit.
2. Add a reviewed official shares-outstanding field/source; re-analyse DE/GB/IT/NO/SE.
3. Extend reviewed German statements beyond DAX (official PDFs/ESEF) for the top-120 liquid names; re-run the six-country audit.
4. Run the APK 0.3.22 device checklist on a real device.
