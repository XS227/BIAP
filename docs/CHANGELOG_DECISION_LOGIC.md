# Decision-logic changelog (protocol deviations from OSF osf.io/6p8y7)

Every change to gates, thresholds, weights or the decision flow made after the OSF registration (2026-10-22) is
recorded here with date, reason, files and whether it is a **protocol deviation**. Data-source or refresh changes
that do not alter a gate or threshold are listed separately as "not a deviation" with the reasoning, so the
paper can show the difference.

Format: `YYYY-MM-DD | Pn.n | what changed | why | files | deviation: yes/no | approved by`

## Changes

Setting: `DECISION_LOGIC_VERSION` (`v1` default, `v2` opt-in; unknown values mean `v1`; `analysis/global_markets/decision_logic.py`).
`v1` is the logic live on 2026-10-30 and is what the frozen paper portfolio and Chapter 4 measure; the investment mode
(`investment_mode.py`) is never switched by this setting and is not modified by any v2 change.

| Date | Item | Change | Why | Deviation | Version |
|---|---|---|---|---|---|
| 2026-11-02 | P1.11 | Additive API field `engines` on `POST /global/analyze` (both engines' decision, score, confidence, logic version) and `engine` on `POST /global/portfolio`; UI labels "Conservative check" / "Investment ranking" on stock detail, Kiasha and Portfolio. No score, gate, threshold or tier changed. | The app showed three scores (0.191 / 0.193 / 0.213) and two decisions for one stock without naming the engine. | no (display and API metadata only) | v1 and v2 |
| 2026-11-02 | P1.10 | `DECISION_LOGIC_VERSION=v2`: agents with confidence < 0.30 (abstaining 0.25, unavailable 0.0) are left out of the conservative score and the decision-confidence mean; confidence is scaled by n/4 when fewer than 4 agents are active. Same rule the investment mode already uses (`data_min_confidence`, `min_agents_full_confidence`). SAP: raw score 0.1963 → 0.2105, decision confidence 0.618 → 0.692. | An abstaining agent held 6.7 % of SAP's weight and pulled the score towards zero. | **yes** for the conservative engine if v2 is activated (changes score and confidence); no for the paper while v1 stays the default (v1 is untouched). Under v2 the investment-mode tiers do change, see the note "Investment mode under v2" below | v2 only |
| 2026-11-02 | P1.3 | `v2`: the Agent 8 disagreement rule (confidence ≥ 0.55, vote ≥ +0.35 vs ≤ −0.35, unchanged limits) is applied only between agents of the same dimension: business = fundamental + quality, market = forecast + liquidity; risk and comparison stand alone. v1 compares any agent with any agent. SAP: quality (+1.0) vs risk (−0.5) no longer triggers REVIEW → HOLD_OR_WATCH is accepted. The investment mode keeps its own rule (`agents_disagree`, tier downgrade) unchanged. | Quality and risk measure different things; a quality company can be volatile. | **yes** for the conservative engine if v2 is activated; no for the paper | v2 only |
| 2026-11-02 | P1.1 / freshness | `v2`: price freshness in the evidence multiplier is interpolated linearly between the v1 anchors (3 d → 1.0, 7 d → 0.65, 30 d → 0.25, 90 d → 0.05) instead of stepping at them. Equal at the anchors and ≤ 3 days; higher between them (e.g. 5 days 0.825 vs 0.65). The hard gate (price > 7 days = `fresh_price` missing = Evidence BLOCK) is unchanged; fundamentals freshness (450/550/730-day steps) is unchanged. | A price that turned 3.01 days old cut the multiplier by 0.105 (Equinor confidence 0.552 → ~0.49). | **yes** for the conservative engine if v2 is activated | v2 only |
| 2026-11-02 | P1.1 display | `v2` messages show confidence with 3 decimals, and with enough extra decimals that a value below the threshold never prints equal to it; the app shows confidence with 3 decimals instead of a rounded percentage (all versions: display only). The comparison operators were already on unrounded values. | "confidence 0.55 below accept threshold 0.55" was display rounding. | no (text only) | v2 messages; app any |
| 2026-11-02 | P1.3 additions (owner, 2026-11-02) | `v2`, both engines: (a) cross-dimension opposition (e.g. fundamental positive, forecast negative) never blocks; it is shown as an informational note (`agentNotes` on `/analyze`, flag `dimension_note` in the investment decision) and in the stock-detail UI; (b) a risk agent at vote ≤ −0.70 with confidence ≥ 0.65 caps the tier instead of a REVIEW: investment mode BUY → ACCUMULATE (flag `risk_cap`), conservative engine BUY_CANDIDATE → HOLD_OR_WATCH (`riskCap` field; the conservative vocabulary has no ACCUMULATE). The investment mode's own disagreement downgrade (`agents_disagree`) now follows the same-dimension rule in v2. Confidence 0.65 for "high" is my choice (the core risk agent emits 0.23–0.82); owner to confirm. | A quality company can be volatile (SAP); an extreme risk reading still must limit the rating. | **yes** (investment-mode v2 differs from v1; v1, which the paper measures, is untouched) | v2 only |
| 2026-11-02 | Portfolio | `v2`: `POST /global/portfolio` builds the portfolio from investment-mode tiers BUY and ACCUMULATE, ranked by investment score and confidence (confidence floor 0.35 kept, the conservative 0.15 score floor not applied). The conservative engine is the risk filter: a stock is excluded when evidence is not PASS, the conservative preliminary call is AVOID_OR_REVIEW, or Agent 9 sets a distress positive_block; scope, FX and price gates unchanged. Response `engine` = Investment ranking with `riskFilter: conservative`. | The conservative engine is almost always empty, so users saw an empty portfolio. | **yes** for the portfolio feature (not a paper measure) | v2 only |
| 2026-11-02 | P1.4 | `v2`: in `freshness.filing_dimension`, peers whose newest report may have been superseded (open quarterly window, known newer filing) or that have no filing date are no longer excluded from the peer benchmark; they stay with their latest available report. Benchmark freshness factor = 1 − 0.30 × (share of such peers); the comparison agent's confidence = 0.65 × factor (0.65 when none). Hard exclusions (explicitly excluded peers, inputs older than the ceiling) still count towards the 15 % limit, which is unchanged. v2 comparison-agent message names the real cause ("peer benchmark not trusted: …") and prints "fewer than 3 same-sector peers" only when that is true. 0.30 is my choice; owner to confirm. Effect on the real caches (read-only run 2026-11-02): SAP gets sector P/E 24.52, vote −0.5 (40 % premium), confidence 0.507 instead of abstaining; Equinor and Aker BP stay without a benchmark because the **quote** dimension fails (Euronext Oslo screening rows have no quote date, `quotesAsOf` is null for all 144 peers), see plan P2.4. | The comparison agent abstained for SAP (73 % undated peers) and the Oslo names (quarterly window) although 12 / 11 same-sector peers with a valid P/E exist. | **yes** for the conservative engine if v2 is activated (the comparison agent now votes, which moves score and BUY rules); the investment mode has its own peer logic, but under v2 its tiers still move through the shared inputs, see the note "Investment mode under v2" below | v2 only |
| 2026-11-02 | P1.4b | `v2`: comparison-agent vote is linear in the P/E discount: `vote = clamp(0.02 × discount%, −0.5, +0.6)` (discount positive = cheaper than the peer median). v1 ladder (0 inside ±15 %, then ±0.3/0.35, caps +0.6/−0.5) is unchanged. Examples (premium): 10 % → −0.2, 20 % → −0.4, ≥25 % → −0.5; (discount) 10 % → +0.2, 20 % → +0.4, ≥30 % → +0.6. | The ladder jumped from 0 to ±0.3 at 15 %, could not tell 30 % from 60 %, and was asymmetric. Owner-approved 2026-11-02. SAP (40 % premium) stays −0.5. | **yes** for the conservative engine if v2 is activated (mid-range companies get a graded instead of a 0/step vote) | v2 only |
| 2026-11-02 | P2.4 | Euronext Oslo quotes are stamped with the last completed session (venue calendar XOSL: close 16:30 + 30 min publish lag, Euronext 2026 holidays, 2027 rule-derived plus 17 May and 26 Dec as a safe superset) and `quoteDateBasis=last_completed_session`; the app labels it "date derived from the trading calendar". Other Euronext markets unchanged. Not behind v2 (a data-labelling fix, not a decision rule). | The Euronext CSV has no trade date, so `quotesAsOf` stayed null and the quote dimension of the Oslo peer benchmark was UNDETERMINED. Owner-approved 2026-11-02. | **no** direct change to a decision; **yes** indirectly: once the Oslo cache is refreshed, Equinor/Aker BP can get a peer benchmark (with P1.4 v2) | takes effect when the Oslo benchmark is refreshed |
| 2026-11-02 | P1.2 | `v2`: low confidence blocks only active calls. (a) `service._call`: below confidence 0.35 a score inside (−0.25, 0.25) is `HOLD_OR_WATCH` instead of `NO_RECOMMENDATION`; BUY_CANDIDATE / AVOID_OR_REVIEW still need confidence ≥ 0.45 and the existing score thresholds. (b) `governance`: a proposed `HOLD_OR_WATCH` is `ACCEPT`ed at any confidence (reason text names the confidence) instead of REVIEW (0.35–0.55) or ABSTAIN (< 0.35). Unchanged: evidence BLOCK (NO_RECOMMENDATION), evidence WARN (REVIEW), scope/distress hard blocks, agent contradictions (REVIEW), every BUY/AVOID gate. | A near-zero score (Equinor 0.043) at confidence below 0.55 was reported as NO_RECOMMENDATION although the neutral call needs no confidence to be safe. | **yes** for the conservative engine if v2 is activated: stocks with a neutral score and confidence < 0.55 move from NO_RECOMMENDATION/REVIEW to HOLD_OR_WATCH (more HOLDs, no new BUY/AVOID); the investment mode is unchanged | v2 only |
| 2026-11-02 | P1.5 | `v2`, conservative engine only: when a positive score reaches `BUY_CANDIDATE` and the **only** reasons governance sends it to REVIEW are missing / too small comparison evidence ("valuation benchmark unavailable …", "sector peer group n (< 8) …"), evidence is PASS and Agent 9 is LOW_RISK / NOT_APPLICABLE, the final call is `HOLD_OR_WATCH` (ACCEPT) with `abstentionCap` = `{qualifier: POSITIVE_RELATIVE_VALUATION_UNVERIFIED, label: "Positive; relative valuation not confirmed", labelFa: "مثبت، ارزش‌گذاری نسبی تأیید نشده"}`; the app shows the label. No new call category. Any other review reason (distress, comparison-only signal, disagreement, WARN) keeps the v1/v2 REVIEW. | Under v2 an abstaining or confidence-discounted comparison agent no longer dilutes the score, so BONHR and EPR (HOLD in v1) crossed 0.25 and ended as NO_RECOMMENDATION. Owner decision 2026-11-02: HOLD_OR_WATCH with a label. Note the cause is partly P1.4: with a 100 % discounted Oslo peer set the comparison agent's confidence is 0.455, below the 0.5 bar in `_critical_data_gaps`, so *no* Oslo BUY can pass the comparison-evidence rule today. | **yes** for the conservative engine if v2 is activated (fewer NO_RECOMMENDATION, more HOLD); investment mode unaffected | v2 only |

## Investigated, not a logic change

### 2026-11-02 — Investment mode under v2 (correction of an earlier statement)

- Earlier entries said the investment mode is "unchanged". That holds for **v1** (untouched, the paper's engine). It does **not** hold for v2: the investment tiers
  are rank-based (percentile within the exchange) on the stored agent signals and the evidence multiplier, so any v2 change to those inputs reshuffles ranks and flags.
- Measured on staging (full replay, 2026-11-02): BUY count **Germany/XETRA 25 → 31**, **Norway 12 → 9** (ACCUMULATE DE 66 → 60, NO 18 → 20; HOLD unchanged; DE 38 and NO 15 tickers change tier).
- Causes (not isolated one by one): (a) comparison inputs - P1.4/P1.4b make the comparison agent vote where it abstained before and with a graded vote; (b) graded price freshness
  changes the evidence multiplier and thus confidence; (c) the v2 flag rules in `investment_mode` - P1.3 same-dimension `agents_disagree`, the cross-dimension note, and the severe-risk cap at ACCUMULATE (`risk_cap`).
  Flags on the changed Norwegian rows are mostly `peer_group_small` and `distress_not_low_risk`; on the German rows `distress_unknown`, `distress_not_low_risk`, `no_peer_comparison`.
- Consequence for the paper: switching v2 on for the investment mode would be a protocol deviation (frozen portfolio 2026-10-20, OSF 6p8y7) and must be logged as such. Until then v2 stays off by default.

### 2026-11-02 — Currency review (P2.5), read-only: no calculation error; paper limitation recorded

- Across the 34 ledgers (latest analysis per stock): 565 stocks report in a currency different from the price currency; 445 are converted with
  date-aligned ECB rates (live since 2026-10-14, `b790055`, i.e. before the paper period of 22 Oct), 17 have no verifiable rate (P/E and per-share ratios withheld),
  103 have no P/E for other reasons. **No stock carries a P/E computed across mismatched currencies.** Peer medians are built from peers converted by the same code.
  Only the currency *label* in the fundamentals table / EPS is open (plan P2.5).
- **Paper limitation (Limitations section of the paper):** 36 stock-days with an investment-mode BUY or SELL tier during the paper period (22 Oct – 1 Nov, 11 daily snapshots)
  were issued without a P/E because no ECB reference rate exists for the reporting currency (GEL, PEN, TWD, KES, NGN, ARS, KRW, MXN; one CAD case without a fixing),
  on 17 tickers in GB:LSE, US:NYSE and US:NASDAQ (examples SEPL, TSM, CHT, AUNA, TEO). The conservative v1 call for these was NO_RECOMMENDATION (one AVOID_OR_REVIEW),
  i.e. fail-closed. The count is an estimate: the ledger keeps only the latest analysis, so earlier days may have had a different FX state.

### 2026-11-02 — Oslo quote date (P2.4): data-line correction, not a decision-logic change (staging run)

- **Classification:** data-line correction. No threshold, rule or weight changed. It **also affects v1 inputs** (the paper's engine): the Oslo scan
  cache gets `screening.quoteDate`/`benchmark.quotesAsOf`, and the API shows `priceDateBasis`. Measured effect on v1 output: see below (none for Equinor / Aker BP).
- **How it was run (production untouched):** backup of `scan-cache/NO/EURONEXT_OSLO.json` (sha256 `1920e4b0…7337`) to
  `~/biap-backups/oslo-cache-20261102T012550Z/`; copy in `~/biap-staging-oslo-20261102/`; `reprice_benchmark` (incremental refresh, Oslo only) run
  from the fix-branch worktree with `BIAP_GLOBAL_DATA_DIR` pointing at the copy and `DECISION_LOGIC_VERSION=v2`. Result OK: 95 of 144 rows repriced
  (49 have no price-dependent multiple), coverage 100 %, `quotesAsOf` 2026-10-30, `quoteDateBasisRetrieved` 0. The production file's hash was unchanged afterwards; no service or timer touched.
- **Re-analysis** (stored company rows from the ledger, `_derive_metrics` onward, same code on all four runs; the v1/before run reproduces the stored 0.0433 / 0.5518 and −0.0004 / 0.5677):

| Stock | Run | Peer benchmark | Comparison vote / conf | Score | Confidence | Call (Agent 8) |
|---|---|---|---|---:|---:|---|
| Equinor | v1, before | stale, abstains ("fewer than 3 peers") | 0 / 0.25 | 0.0433 | 0.5518 | HOLD_OR_WATCH (ACCEPT) |
| Equinor | v1, after | **still stale** (quarterly window drops all 95 peers), abstains | 0 / 0.25 | 0.0433 | 0.5518 | HOLD_OR_WATCH (ACCEPT) |
| Equinor | v2, before | not trusted: quote date missing, abstains | 0 / 0.25 | 0.0467 | 0.6144 | HOLD_OR_WATCH (ACCEPT) |
| Equinor | v2, after | **valid**, 12 same-sector peers, sector P/E 18.01 | −0.465 / 0.455 | −0.0141 | 0.5844 | HOLD_OR_WATCH (ACCEPT) |
| Aker BP | v1, before | stale, abstains | 0 / 0.25 | −0.0004 | 0.5677 | HOLD_OR_WATCH (ACCEPT) |
| Aker BP | v1, after | still stale, abstains | 0 / 0.25 | −0.0004 | 0.5677 | HOLD_OR_WATCH (ACCEPT) |
| Aker BP | v2, before | not trusted, abstains | 0 / 0.25 | −0.0004 | 0.6335 | HOLD_OR_WATCH (ACCEPT) |
| Aker BP | v2, after | valid, sector P/E 18.01 | −0.5 / 0.455 | −0.0579 | 0.6003 | HOLD_OR_WATCH (ACCEPT) |

- **Reading:** under v1 the data fix changes nothing for these two stocks, because v1 still discards every peer in the open quarterly window (P1.4 v2 is what
  keeps them). Under v2 the benchmark becomes usable and the comparison agent votes. The v2 confidence difference between "before" columns and v1 comes from the graded
  price freshness (an earlier v2 change), not from this fix. Aker BP's P/E of 179.8 (898 % premium) is **not** an FX error (correction 2026-11-02: an earlier version of this note said it was): EPS USD 0.21 x 10.3883 (ECB FY2025 mean USD->NOK) = NOK 2.18, price 392.3 / 2.18 = 179.8. It comes from very low reported net income (USD 132 m). Equinor's 22.2 is converted the same way and correct.
- **Not recomputed:** the investment-mode tier (own peer logic, unchanged by P1.4/P2.4; stored tier HOLD for both on every snapshot day).

### 2026-11-02 — BLOCK count fell from 4,454 to 1,228 between 28 and 29 Oct (Phase 0)

- Measured from `/var/lib/biap-global/daily-snapshots` (23:40Z snapshots, 12 markets): BLOCK 7,530 (27 Oct) → 4,454 (28 Oct)
  → 1,228 (29 Oct) → 1,227 (30 Oct). The plan's "~4,750" does not match any snapshot (4,454 is the 28 Oct figure); it was probably
  read from a live ledger at another moment. PASS rose 3,087 → 6,314.
- 28→29 Oct, BLOCK→PASS per market: US:NASDAQ 2,523→756, US:NYSE 1,076→187, GB:LSE 454→95, SE:Stockholm 185→28,
  ES:Madrid 46→6, IT:Milan 35→22. FI, FR, NL, NO and DE:XETRA did not change.
- Cause: the first production run of the new price-refresh timers (EU 2026-10-29 17:00Z, US 21:15Z; both `head=6c8ada1`, exit 0)
  fully re-analysed every market. The rows that flipped were last analysed on 28 Oct (≈11:36Z–12:06Z) and were re-analysed
  on 29 Oct (17:34Z–21:34Z) with the **same** fundamental source (e.g. 1,675 US rows `sec-edgar-xbrl-cached`, 345 GB rows
  `official-oam-gb-fca-nsm`). Only price/date/analysis time changed. The earlier BLOCKs were the `fresh_price` evidence gate
  (company price older than 7 days while the screener quote was current; see `claude-us-se-block-investigation-20261029.md` and the
  live-stability notes of 2026-10-30), which a fresh price clears.
- Also in that window (data-source fixes, no gate change): `2b6864c` GB Yahoo vendor close (28 Oct), `2599b91` online-first refresh returns the
  fresh upstream price (28 Oct), `31eec5a` verified LSE vendor close over stale cache (29 Oct 01:05Z). I did not establish
  which of these were running in the live service at which minute.
- No change to `agents.py`, `governance.py`, `service.py::_call` or `investment_mode.py` thresholds is visible in that window
  (the `git log` for 27–30 Oct shows only data-source, mobile and docs commits). The snapshot manifests record the same
  `decisionConfig` on all four days. Note: their `engine.commit` field is the constant `c3d3bc7` (a 20 Oct commit), so it cannot be used as proof
  of the running engine version.
- Conclusion: **not a gate or threshold change, therefore not a protocol deviation**, but a data-pipeline effect that moved ~3,200 stocks
  out of BLOCK. Any before/after funnel in the paper must state that the 28 Oct figures were taken before the first full
  refresh. Owner to confirm this classification.
- Limits: the old per-row BLOCK reason was overwritten by the re-analysis (snapshots keep only "evidence BLOCK"), so `fresh_price` as the
  reason for every flipped row is inferred from the investigation notes and the unchanged fundamentals, not read from stored data.
  Remaining BLOCKs are mostly `missing:fundamental_source` (US) per the 29 Oct note.

### 2026-11-02 — tests that assume v1 (for the day v2 is activated)

Forcing `DECISION_LOGIC_VERSION=v2` over the existing suite failed six conservative-engine tests (and two investment-mode tests) that assert the v1 any-vs-any
disagreement rule. Owner decision: they stay as they are (v1) and v2 versions are written separately:
`tests/test_decision_logic_v2_conservative.py` (the six), `tests/test_decision_logic_v2_agents.py` (investment mode and payload),
`tests/test_decision_logic_v2_portfolio.py`. `tests/conftest.py` pins every test to v1 unless it opts in, so the suite no longer depends on the shell environment.
Consequence worth knowing: under v2 the AAPL-like case (comparison −0.5 premium vs fundamental +0.55) is no longer a contradiction, so a BUY_CANDIDATE is accepted
when the fresh peer benchmark exists (`test_v2_premium_valuation_against_strong_fundamentals…`); the BUY rules in the live path (peer group ≥ 8, distress, independent signal) remain. `test_global_mobile_release::test_manifest_matches_global_app_version` fails on the base as well (known, unrelated).
