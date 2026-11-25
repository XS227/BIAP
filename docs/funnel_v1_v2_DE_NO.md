# Rejection funnel, v1 vs v2 (all fixes up to P1.2) — Germany (XETRA) and Norway (Oslo)

Compiled 2026-11-02. **Read-only for production, everything on staging.** Branch `fix/biap-fix-plan-20261102` at P1.2 (`1a0a096`).
v2 = `DECISION_LOGIC_VERSION=v2` with P1.3, P1.4 (+P1.4b linear comparison vote), P1.10, P1.11, graded price freshness and P1.2. **P1.5 and P1.6 are not in yet.**

## Method

- Ledger copies of `DE__XETRA` and `NO__EURONEXT_OSLO` (taken 2026-11-02 ~01:19Z) were put into two staging data dirs (`~/biap-staging-funnel-v1`, `-v2`).
  Every stored company was replayed (`_derive_metrics` → agents → evidence → distress → `_analysis_payload`, no network, no re-enrichment) and the
  result written into the **staging** ledger; the funnel numbers come from the repo's own `ranking_gate_counts`, `ranking_groups` and `decision_overlay.market_view`.
- Staging scan caches: Oslo = the refreshed benchmark (quote date derived, see changelog P2.4); XETRA = copy of the production cache.
- **Fidelity check (v1 replay vs stored):** XETRA 408 of 408 identical call and score; Oslo 144 of 146 (two rows differ). The v1 replay reproduces the numbers on the Market page: Oslo 111 ranked / 94 NO_SIGNAL / 16 HOLD / 1 AVOID; XETRA 33 ranked / 25 NO_SIGNAL / 7 HOLD / 1 AVOID.
- Limits: replay starts from stored enriched companies, so provider/source changes since the last analysis are not reflected; Frankfurt (DE:FRANKFURT) is not included.

## 1. Funnel

| Stage | DE v1 | DE v2 | NO v1 | NO v2 |
|---|---:|---:|---:|---:|
| Universe discovered | 411 | 411 | 144 | 144 |
| Analysed | 407 | 407 | 144 | 144 |
| Evidence PASS (rest: WARN / BLOCK) | 373 (19 / 15) | 373 | 134 (0 / 10) | 134 |
| Score and confidence available | 373 | 373 | 134 | 134 |
| Ranking-evidence standard (core statements, coverage ≥ 60 %) = **ranked** | 33 | 33 | 111 | 111 |
| *Conservative engine, among ranked:* BUY_CANDIDATE | 0 | **1** | 0 | 0 |
| HOLD_OR_WATCH | 7 | **27** | 16 | **73** |
| AVOID_OR_REVIEW | 1 | **5** | 1 | **13** |
| NO_RECOMMENDATION ("No signal") | 25 | **0** | 94 | **25** |
| Governance action REVIEW (all analysed rows) | 374 | 72 | 113 | 30 |

Investment-mode tiers (the badges on the Market list; ledger-wide, evidence-capped):

| Tier | DE v1 | DE v2 | NO v1 | NO v2 |
|---|---:|---:|---:|---:|
| BUY | 25 | 31 | 12 | 9 |
| ACCUMULATE | 66 | 60 | 18 | 20 |
| HOLD | 202 | 202 | 68 | 68 |
| REDUCE | 60 | 59 | 20 | 20 |
| SELL | 38 | 39 | 13 | 13 |
| NO_RECOMMENDATION | 16 | 16 | 13 | 14 |

- Germany's real bottleneck is the **ranking-evidence standard**, not the decision logic: only 33 of 373 evidence-PASS stocks have complete core statements, so 340 sit in "Insufficient evidence" in both versions.
- **The investment tiers also move under v2** (DE BUY 25→31; NO BUY 12→9). Earlier changelog wording said the investment mode is unchanged; that is true for v1 only (corrected 2026-11-02, see the changelog note "Investment mode under v2"). The movement comes from the shared v2 changes (P1.10 abstaining agents carry no weight, P1.3, graded freshness). If v2 were ever switched on for the investment mode, that is a protocol-relevant change for the paper (frozen portfolio 2026-10-20).

## 2. The 94 (Norway) and 25 (Germany) "no recommendation"

- **Engine: the conservative engine.** They are the `NO_SIGNAL` group of the Market page's ranking groups (`call = NO_RECOMMENDATION` among ranked stocks). The investment-mode tiers are a different list: its NO_RECOMMENDATION is only 13 (NO) / 16 (DE), all evidence BLOCK (10 / 15) or Agent 9 distress block (3 / 1).
- Why they were NO_RECOMMENDATION in v1 (governance / `_call` gate):

| v1 cause | NO (94) | DE (25) |
|---|---:|---:|
| Confidence below the accept threshold on a **neutral** call (HOLD) — fixed by P1.2 | 58 | 12 |
| Confidence gate on an active call (BUY/AVOID candidate below 0.55) | 12 | 3 |
| High-confidence agent disagreement (any-vs-any rule) — P1.3 | 18 | 9 |
| BUY rule (distress not LOW_RISK / peer group < 8 / comparison-only) | 4 | 1 |
| Agent 9 distress hard block | 2 | 0 |

- Where they went in v2:

| v1 NO_RECOMMENDATION → v2 | NO (94) | DE (25) |
|---|---:|---:|
| HOLD_OR_WATCH | 59 | 20 |
| AVOID_OR_REVIEW | 12 | 4 |
| BUY_CANDIDATE (accepted) | 0 | 1 (IXX, score 0.295, confidence 0.649, benchmark valid, all BUY rules passed) |
| still NO_RECOMMENDATION | 23 | 0 |

- **Regression to look at (Norway):** two stocks that were HOLD in v1 became NO_RECOMMENDATION in v2: **BONHR** and **EPR**. In v2 an abstaining comparison agent no longer dilutes the score, the score crosses 0.25 and the preliminary call becomes BUY_CANDIDATE, which the BUY rules then block for lack of a valuation benchmark ("a BUY requires verified comparison evidence"; EPR also has a peer group of 6). That is exactly the case P1.5 (capped fallback when only the comparison agent abstains) is meant to handle.

## 3. Still NO_RECOMMENDATION in v2 — the gate that stops them

Germany: none (0). Norway: 25 (23 that were already blocked in v1 plus BONHR and EPR), by main gate:

| Gate | Count | Examples |
|---|---:|---|
| Confidence gate on an **active** call (BUY or AVOID candidate, confidence < 0.55) | 10 | HYPRO, TECH, NOM, NAVA |
| BUY rule: distress not LOW_RISK, peer group < 8, or comparison-only | 7 | MEDI, DOFG, EPR, BNOR |
| High-confidence agent disagreement (v2 same-dimension rule; these are genuine same-dimension conflicts) | 5 | PNOR, WSTEP, MPCC, BOUV |
| Critical data gap (valuation benchmark unavailable) | 2 | ABG, BONHR |
| Agent 9 distress hard block | 1 | MORLD |

Not counted here (they are not "ranked" and never reach this list): the 33 Norwegian and 374 German stocks in "Insufficient evidence", and the evidence BLOCK/WARN stocks.

## Open points for the owner

1. BONHR / EPR regression → decide P1.5 (capped ACCUMULATE-type outcome vs. HOLD) before v2 is activated.
2. The 5 remaining disagreement cases use the v2 same-dimension rule (`evidence_agent` calls `disagreement_v2`), so they are genuine same-dimension conflicts; the REVIEW-for-disagreement workflow itself is still open (P1.3).
3. Germany needs the statement-standard work (P2.x / data), not more decision-logic changes, to rank more than 33 names.
