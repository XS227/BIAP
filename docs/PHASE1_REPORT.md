# Phase 1 final report — BIAP Global decision layer

Compiled 2026-11-02. Branch `fix/biap-fix-plan-20261102` (head before this report: `5d15da9`, P1.6).
Production (`/home/ubuntu/biap-global/BIAP`, branch `main`, `6c8ada1`) is **untouched**: nothing below is live.
Everything measured here comes from **staging replays** (no network, production data dir never written).
Source of truth for each rule change: `docs/CHANGELOG_DECISION_LOGIC.md`. Plan: `docs/BIAP_FIX_PLAN.md`.

Convention: **v1** = logic live on 2026-10-30 (default, measured by the paper). **v2** = `DECISION_LOGIC_VERSION=v2`, opt-in, not enabled anywhere except staging.

---

## 1. Phase 1 items and status

"Done" means implemented, tested and replayed on staging **behind the v2 flag, awaiting owner approval**. Nothing is in production.

| Item | Status | What exists | What is still open |
|---|---|---|---|
| P1.1 Agent 8 threshold display | **Done** (display) | 3-decimal confidence in v2 messages and in the app. The comparison itself was already on unrounded values, so "0.55 below 0.55" was rounding in the text, not a wrong operator. | Many Oslo names still sit at 0.50–0.57; that is handled by P1.2/graded freshness, not by this item. |
| P1.2 No confidence gate on neutral calls | **Done** (v2) | Score inside (−0.25, +0.25) is HOLD_OR_WATCH at any confidence; BUY/AVOID gates unchanged. | — |
| P1.3 Disagreement rule | **Done** (v2), workflow **open** | Same-dimension rule (business = fundamental+quality; market = forecast+liquidity; risk and comparison stand alone). Cross-dimension opposition is an informational note. Severe risk (vote ≤ −0.70, conf ≥ 0.65) caps BUY→ACCUMULATE / BUY_CANDIDATE→HOLD_OR_WATCH. | A real reviewer workflow for REVIEW does not exist, so genuine disagreements stay stuck (see §2, "remaining"). Owner to confirm the 0.65 "high" confidence I chose. |
| P1.4 / P1.4b Comparison agent peer benchmark | **Partly done** (v2) | Peers in an open quarterly window or without filing date stay at a 0.30 freshness discount instead of being dropped; message names the real cause; linear vote `clamp(0.02×discount%, −0.5, +0.6)`. | Oslo needs a cache refresh (separate approval) and, for BUY, P2.3 (interim reports): with every peer discounted the comparison confidence is 0.455 < 0.5, so no Oslo BUY can pass. The 0.30 factor is my choice; owner to confirm. |
| P1.5 Abstention fallback | **Done** (v2) | Only-comparison-unverified positive score → HOLD_OR_WATCH labelled "Positive; relative valuation not confirmed" (owner decision: no new category). | — |
| P1.6 "If already owned" never "No Action" | **Done** (v2) | NO_RECOMMENDATION → `HOLD_AND_MONITOR` + note. Display/mapping only. | — |
| **P1.7 BUY threshold calibration** | **Not started** | Only the dilution part is covered, by P1.10 (abstaining agents carry no weight). | Everything else. Proposal below. |
| **P1.8 Agent 9 / Agent 10 consistency** | **Not started** | — | Everything. Proposal below. |
| **P1.9 Show the blocking gate** | **Not started** | v2 messages name the real cause (P1.4/P1.5 wording) and the replay script classifies the gate, but the app shows no "blocked by" field. | Everything in API and UI. Proposal below. |
| P1.10 Abstaining agents carry no weight | **Done** (v2) | Agents with confidence < 0.30 are left out of score and confidence mean. | — |
| P1.11 Two engines explicit | **Done** (all versions, display only) | `engines` block in the API; UI labels "Conservative check" / "Investment ranking". | Methodology text must still state which engine the paper measures. |

So **P1.7, P1.8 and P1.9 were not done**. Proposals:

**P1.7 — recommendation: do not change the BUY threshold now; run a report-only calibration study first.**
- The "compressed scores" premise holds for Germany and France, not everywhere. Evidence-PASS stocks, v2 (staging):

  | Market | n | median | p90 | max | score ≥ 0.25 | and confidence ≥ 0.55 |
  |---|---:|---:|---:|---:|---:|---:|
  | DE:XETRA | 373 | −0.082 | 0.098 | 0.295 | 2 | 1 |
  | FR:Paris | 260 | −0.017 | 0.134 | 0.298 | 2 | 2 |
  | NO:Oslo | 134 | 0.003 | 0.237 | 0.444 | 10 | 7 |
  | SE:Stockholm | 373 | 0.009 | 0.192 | 0.339 | 17 | 17 |
  | GB:LSE | 426 | 0.013 | 0.199 | 0.415 | 19 | 19 |
  | US:NYSE | 1593 | 0.070 | 0.236 | 0.453 | 127 | 94 |

  (All evidence-PASS rows, not only the "ranked" ones. The plan's DE "average 0.039" is not reproduced by this population; mean here is −0.091. I did not find which population the plan used.)
- A percentile-based BUY threshold guarantees a BUY share whatever the data quality, which is exactly what the investment mode already does (rank-based tiers). Putting it into the conservative engine too would blur the two engines that P1.11 just separated.
- Germany's low scores are mostly a data problem (only 33 of 373 are ranked), so recalibrating there would hide it.
- Proposed work, in order: (1) report-only: score and confidence distributions per market for ranked stocks only, plus the effect of 0.20/0.25/0.30 on BUY_CANDIDATE counts (no code change); (2) owner decides whether the conservative engine keeps absolute thresholds (my recommendation) and the percentile view stays in the investment mode; (3) any threshold change is an OSF protocol deviation, logged with date and reason, and goes in v2 only.

**P1.8 — recommendation: Altman Z'' must not set the safety gate alone for capital-intensive sectors; show the governing model.**
- Not investigated in code yet; the Aker BP facts (Z'' 1.06 high risk, Zmijewski unlikely, Agent 10 rating A, PD 0.05 %) come from the plan, not from a re-run.
- Proposed: exempt Altman Z'' as a sole trigger for oil & gas, utilities, shipping (ICB-based list, owner to approve); there the gate needs a second model to agree; add a `governingModel` + reason to the Agent 9 payload and the detail page; v2 only; tests first on Aker BP and one utility. Check first whether Agent 10 is in the BIAP Global path at all, then decide the scope.

**P1.9 — recommendation: do it next; low risk.**
- Add an additive `blockingGate` object (`code`, `label`, `detail`) derived from the governance reasons already stored (the categories in the replay script: confidence gate on an active call, high-confidence disagreement, BUY rule, comparison/benchmark unavailable, distress hard block, evidence standard), shown on the detail page and as a short tag on the list row. Display metadata like P1.11: no gate or threshold changes, so it can ship for v1 too.

---

## 2. Rejection funnel, v1 vs v2, all active markets (after P1.5 and P1.6)

Active = the 12 exchanges in `INVESTMENT_MODE_MARKETS` (11 markets; DE is Xetra + Frankfurt). Denmark has a cache but is outside the investment scope, shown for reference.
Staging replay of every stored company at head `5d15da9` (written 2026-11-02 02:21–02:24Z, after P1.5 and P1.6). The call columns are the **conservative engine among ranked stocks**; B = BUY_CANDIDATE, H = HOLD_OR_WATCH, A = AVOID_OR_REVIEW, N = NO_RECOMMENDATION. P1.6 changes only the holder answer, so it does not move these counts.

| Market | Universe | Analysed | Evidence PASS | Ranked (statement standard) | Unranked share of PASS | v1 B/H/A/N | v2 B/H/A/N | Bottleneck |
|---|---:|---:|---:|---:|---:|---|---|---|
| DE:XETRA | 411 | 407 | 373 | 33 | **91 %** | 0/7/1/25 | 1/27/5/0 | **Data** (core statements incomplete / coverage < 60 %); decision layer no longer binding |
| DE:Frankfurt | 501 | 494 | 435 | 34 | **92 %** | 0/9/1/24 | 0/25/9/0 | **Data**, same cause |
| NO:Oslo | 144 | 144 | 134 | 111 | 17 % | 0/16/1/94 | 0/78/13/20 | v1: **decision layer** (94 of 111). v2: decision fixed; **BUY now blocked by data** (peer freshness, comparison confidence 0.455 < 0.5, see P2.3) |
| SE:Stockholm | 401 | 401 | 373 | 264 | 29 % | 0/76/1/187 | 0/194/29/41 | v1 **decision layer**; v2 residual: 30 genuine disagreements, 7 active-call confidence |
| FI:Helsinki | 147 | 145 | 122 | 105 | 14 % | 0/21/1/83 | 0/84/10/11 | v1 **decision layer**; v2 residual small (7 disagreement, 4 confidence) |
| FR:Paris | 294 | 293 | 260 | 181 | 30 % | 0/21/0/160 | 0/127/20/34 | v1 **decision layer**; v2 residual: 18 active-call confidence, 15 disagreement; 112 unranked = data |
| NL:Amsterdam | 97 | 97 | 82 | 62 | 24 % | 0/13/0/49 | 0/42/9/11 | v1 **decision layer**; v2 residual 11 |
| IT:Milan | 193 | 193 | 171 | 131 | 23 % | 0/3/0/128 | 0/104/10/17 | v1 **decision layer**; v2 residual: 13 disagreement |
| ES:Madrid | 109 | 106 | 100 | 76 | 24 % | 1/14/2/59 | 1/56/4/15 | v1 **decision layer**; v2 residual: 9 active-call confidence |
| GB:LSE | 527 | 522 | 426 | 299 | 30 % | 5/38/0/256 | 12/225/30/32 | v1 **decision layer**; v2 residual: 18 disagreement, 11 confidence, 3 distress hard blocks; 223 outside ranking = data |
| US:NASDAQ | 3015 | 3007 | 2250 | 1579 | 30 % | 0/98/5/1476 | 0/1134/362/83 | v1 **decision layer**; v2 residual: 47 disagreement, 21 confidence |
| US:NYSE | 1790 | 1780 | 1593 | 1106 | 31 % | 0/168/1/937 | 2/903/106/95 | v1 **decision layer**; v2 residual: 68 disagreement, 14 BUY rule |
| *DK:Copenhagen (not in scope)* | 116 | 116 | 99 | 76 | 23 % | 2/16/1/57 | 6/49/3/18 | v1 decision layer |

Reading:
- **Data is the binding constraint in Germany only** (≈ 91–92 % of evidence-PASS stocks never reach ranking). Elsewhere 14–31 % are lost at the statement standard.
- **The decision layer was the binding constraint everywhere else under v1**: 71–98 % of ranked stocks ended as NO_RECOMMENDATION (e.g. IT 128 of 131, FR 160 of 181, NO 94 of 111). Under v2 that falls to 0–20 %.
- **BUY_CANDIDATE stays rare under v2** (22 in total across the 13 exchanges listed: 12 GB, 6 DK, 2 NYSE, 1 XETRA, 1 ES). The conservative engine is still almost always HOLD/AVOID. That is the open P1.7 question, plus P2.3 for Oslo, and it is not an error of v2.
- What remains as NO_RECOMMENDATION in v2 is mostly **genuine same-dimension disagreement** (needs the P1.3 reviewer workflow) and **low confidence on an active call** (a working gate, not a bug).

Caveats you should know before quoting these numbers:
1. **v1 replay fidelity is not 100 % everywhere.** Replay reproduces the stored v1 call and score for DE:XETRA 408/408, Frankfurt 489/496, SE 397/402, FR 283/295, NL 94/98, NASDAQ 3009/3019, NYSE 1783/1791, FI 145/146, NO 144/146. It does **not** for **IT (37/193), GB (394/816), DK (17/116)** and several out-of-scope markets (BE, BR, IE, IS, PT, TR). Cause found 2026-11-02: the replay used today's clock and scan-cache; with `tools/asof_replay.py` IT 193/193, GB 522/522, DK 116/116 match (docs/REPRODUCIBILITY_ASOF_REPLAY.md). For those markets the "v1" columns are the **replayed** v1, not the stored one, and v1-vs-v2 differences are still like-for-like (same inputs, same replay).
2. Replay starts from stored enriched rows. Provider or source changes after the last analysis are not reflected. Frankfurt is included here (it was not in the earlier DE/NO note).
3. The Oslo peer benchmark in this run uses the staging copy refreshed with the derived quote date (P2.4); production's Oslo cache is still undated.
4. Funnel numbers are counts on a single day's ledger; the 28 Oct BLOCK figures in the paper predate the first full refresh (changelog, Phase 0).

---

## 3. What changed in v2 (behaviour list)

Each line is also in `docs/CHANGELOG_DECISION_LOGIC.md` with date and files. "Deviation" = would be an OSF protocol deviation (osf.io/6p8y7) **if v2 is activated**; while v1 stays default there is none.

Conservative engine
1. **Abstaining agents carry no weight** (confidence < 0.30 left out of score and confidence; confidence scaled by n/4 below 4 active agents). SAP 0.196 → 0.2105, confidence 0.618 → 0.692.
2. **Disagreement is same-dimension only**; cross-dimension opposition is a note; a severe risk reading caps the tier instead of forcing REVIEW.
3. **Graded price freshness** (linear between 3/7/30/90 day anchors) instead of steps; the 7-day hard gate is unchanged.
4. **Neutral calls are not confidence-gated** (P1.2); BUY/AVOID gates unchanged.
5. **Peer benchmark keeps discounted peers** (factor 1 − 0.30 × share of affected peers; comparison confidence 0.65 × factor) and the comparison message states the true cause; **linear comparison vote** replaces the step ladder.
6. **Unverified relative valuation** on a positive score → HOLD_OR_WATCH with the label "Positive; relative valuation not confirmed" (P1.5); BUY-suspended message names the real cause.
7. **"If already owned"** for NO_RECOMMENDATION → HOLD_AND_MONITOR (P1.6).
8. 3-decimal confidence in messages.

Investment mode / portfolio
9. **Investment-mode tiers move under v2.** The mode was described as "unchanged"; that is true only for v1. Tiers are rank-based on the stored agent signals and the evidence multiplier, so every shared v2 change reshuffles them. Staging replay, 12 active exchanges:

   | Tier | v1 | v2 | Δ |
   |---|---:|---:|---:|
   | **BUY** | **449** | **509** | **+60 (+13 %)** |
   | ACCUMULATE | 957 | 896 | −61 |
   | REDUCE | 1131 | 954 | −177 |
   | **SELL** | **455** | **632** | **+177 (+39 %)** |

   BUY per exchange (v1 → v2): XETRA 25→31, Frankfurt 27→32, **Oslo 12→9**, SE 25→27, FI 9→10, FR 23→24, NL 6→7, IT 15→16, ES 3→4, GB 28→34, NASDAQ 152→182, NYSE 124→133. The BUY gain is almost entirely promotions from ACCUMULATE. The large SELL increase comes from the two US exchanges (NASDAQ SELL 147→225, NYSE 65→159, with REDUCE falling by the same amount). Per-cause attribution of this US shift is **not done**; likely the comparison vote becoming graded and the freshness change, but that is a guess.
   Cause of the changes is shared inputs (items 1–5), the v2 flag rules in `investment_mode` (same-dimension `agents_disagree`, cross-dimension note, severe-risk cap), not a changed rank rule.
   **Consequence:** switching v2 on for the investment mode is a protocol deviation (frozen paper portfolio 2026-10-20). Until then v2 stays off.
10. `POST /global/portfolio` under v2 builds from investment tiers BUY+ACCUMULATE with the conservative engine as risk filter (no more empty portfolio when there are 0 conservative BUYs).

Not behind v2 (all versions)
11. P1.11 engine labels and API `engines` block (display only).
12. P2.4 Oslo quote date stamped with the last completed session (data-line fix; changes the **v1 input** for Oslo once its cache is refreshed; classified as a data-line correction, not a gate change; owner to confirm).
13. App version 0.3.23 manifest alignment (not a decision change).

---

## 4. Production rollout plan (plan only, nothing executed) and keeping v1 intact for the paper

**Facts this plan rests on** (checked 2026-11-02): production runs from `/home/ubuntu/biap-global/BIAP` on `main` (`6c8ada1`), `biap-global.service` + `biap-global-analysis-worker.service`, data in `/var/lib/biap-global`, price-refresh timers EU 17:00Z / US 21:15Z, daily snapshots 23:40Z. The decision version is a **process-level environment variable** (`DECISION_LOGIC_VERSION`), and analysis **writes results into the ledger**: a v2 process pointed at the production data dir would overwrite the v1 history. That drives the whole plan. Test suite: `tests/conftest.py` pins every test to v1 unless a test opts in.

**Paper test period (owner, 2026-11-02): OSF registration 23 Oct 2026; statistics are taken until 19 Nov 2026, so the period is 23 Oct – 19 Nov. Rows dated 22 Oct are not part of the prospective period. The owner will confirm the exact end date from the OSF record; treat 19 Nov as the working date, not as final.** v1 stays untouched on production until then (v2 in production not before the period ends).

### Stage 0 — decisions needed before anything moves (owner)
- Approve/reject each v2 item (§3) and the two constants I chose (0.30 peer discount, 0.65 "high" risk confidence).
- Classify P2.4 (Oslo date) and the BLOCK drop (Phase 0) as non-deviations, or log them as data-line corrections.
- PR #74 (ChatGPT branch) still unmerged: merge or close it first so the two lines do not conflict.

### Stage 1 — ship the code, behaviour stays v1
1. Open a PR `fix/biap-fix-plan-20261102` → `main`; full test suite green; `scripts/regression_check.py --strict` on the frozen snapshot (per-tier change > 5 % = fail).
2. Extra proof that v1 is untouched: replay the frozen paper tickers under v1 on the branch and compare call and score with the stored values (target: identical; XETRA already 408/408). Any difference must be explained by P2.4 or a display change before merging.
3. Pre-deploy backups: tag current prod commit (`live-pre-p1-<date>`), copy `/var/lib/biap-global` ledgers and scan caches (sha256 manifest), copy the unit files. Keep the 2026-10-30 tag `live-20261030` and its rollback script.
4. Deploy in a quiet window (not 16:30–17:30Z or 21:00–22:00Z, not 23:30–23:50Z). `DECISION_LOGIC_VERSION` stays **unset** (= v1). Restart `biap-global` and the worker. Smoke: `/global/analyze` for SAP, Equinor, Aker BP returns the same call/score as before plus the new `engines` block; Market page counts equal the previous day's snapshot.
5. Ship the mobile build only after the API is verified (app 0.3.23 manifest already aligned).

### Stage 2 — v2 side by side, separate data
1. Create a **second service instance** (own port, own `BIAP_GLOBAL_DATA_DIR`, copy of the ledgers and caches, `DECISION_LOGIC_VERSION=v2`, no timers writing to production). This unit does not exist yet and must be built; verify before relying on it that its refresh and worker units cannot touch `/var/lib/biap-global`.
2. Use it for the owner's review and the Phase 4 acceptance runs (per-market funnels, before/after figures for the paper). Do not expose it to app users.
3. Optional: serve it in the app behind an explicit "preview" switch for named testers only.

### Stage 3 — activate v2 in production (not before the paper period ends)
1. Preconditions: paper evaluation closed and the frozen snapshot re-hashed; all Stage 0 approvals; Oslo cache refresh approved and done (otherwise Oslo BUYs stay suspended); P1.9 shipped so users can see blocking gates; P2.3 scheduled.
2. Fresh backup; set `DECISION_LOGIC_VERSION=v2` in the unit environment; restart; run a full re-analysis through the worker (not by hand); compare against the Stage 2 funnel; announce the change with the changelog and the `engines` block showing `v2`.
3. Log the activation date in the changelog as the day the production decision logic changed.

### Rollback
| Situation | Action | Time | Data effect |
|---|---|---|---|
| Stage 1 behaves differently from v1 | Check out the tag `live-pre-p1-<date>`, restart the two services | minutes | None: flag was unset, ledger written only by v1 logic |
| Stage 3 v2 misbehaves | Remove `DECISION_LOGIC_VERSION` (= v1), restart; **then restore the pre-activation ledger backup** | minutes + restore | v2 re-analysis wrote v2 results into the ledger. Re-analysing under v1 does **not** reproduce the old ledger for every market (replay fidelity above: IT, GB, DK differ), so the backup, not a re-run, is the rollback |
| Bad data from P2.4 / Oslo refresh | Restore the Oslo scan-cache backup (`~/biap-backups/oslo-cache-20261102T012550Z/`, sha256 `1920e4b0…7337`) | seconds | Oslo only |
| Mobile build problem | Previous manifest/version stays published; API additions are additive | — | None |

### How v1 stays untouched for the paper until the end of the period
1. **Production decision version stays v1** (`DECISION_LOGIC_VERSION` unset) through the whole period; Stage 1 changes code but not logic. v2 runs only in a separate process with a separate data directory.
2. **Frozen artefacts are not re-derived**: the research snapshot (`~/biap_research/snapshot_2026-10-19`, read-only 0444 files, sha256 manifest) and `research/paper_portfolio_2026-10-20.json` stay as they are; the paper's analyses read only from the snapshot.
3. **The v1 time series continues unbroken**: daily 23:40Z snapshots, the paper equity snapshot timer and the performance evaluator keep running on v1.
4. **Guards**: tests pinned to v1 by default; `regression_check.py --strict` and the paper-ticker v1 replay before each deploy; add a check that the running service reports `logicVersion = v1` in `engines` (a failing check blocks the day's deploy).
5. **Anything that does change v1 inputs is labelled**, not hidden: P2.4 (Oslo date) and future data fixes (P2.1–P2.3) are logged as data-line corrections with date; the paper must state which funnels were taken before/after them.
6. **No v2 switch for the investment mode before the end date** (§3, item 9): the tier counts above show it would change BUY/SELL materially.
