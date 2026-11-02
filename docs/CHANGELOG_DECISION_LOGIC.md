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
| 2026-11-02 | P1.10 | `DECISION_LOGIC_VERSION=v2`: agents with confidence < 0.30 (abstaining 0.25, unavailable 0.0) are left out of the conservative score and the decision-confidence mean; confidence is scaled by n/4 when fewer than 4 agents are active. Same rule the investment mode already uses (`data_min_confidence`, `min_agents_full_confidence`). SAP: raw score 0.1963 → 0.2105, decision confidence 0.618 → 0.692. | An abstaining agent held 6.7 % of SAP's weight and pulled the score towards zero. | **yes** for the conservative engine if v2 is activated (changes score and confidence); no for the paper (investment mode untouched, v1 default) | v2 only |
| 2026-11-02 | P1.3 | `v2`: the Agent 8 disagreement rule (confidence ≥ 0.55, vote ≥ +0.35 vs ≤ −0.35, unchanged limits) is applied only between agents of the same dimension: business = fundamental + quality, market = forecast + liquidity; risk and comparison stand alone. v1 compares any agent with any agent. SAP: quality (+1.0) vs risk (−0.5) no longer triggers REVIEW → HOLD_OR_WATCH is accepted. The investment mode keeps its own rule (`agents_disagree`, tier downgrade) unchanged. | Quality and risk measure different things; a quality company can be volatile. | **yes** for the conservative engine if v2 is activated; no for the paper | v2 only |
| 2026-11-02 | P1.1 / freshness | `v2`: price freshness in the evidence multiplier is interpolated linearly between the v1 anchors (3 d → 1.0, 7 d → 0.65, 30 d → 0.25, 90 d → 0.05) instead of stepping at them. Equal at the anchors and ≤ 3 days; higher between them (e.g. 5 days 0.825 vs 0.65). The hard gate (price > 7 days = `fresh_price` missing = Evidence BLOCK) is unchanged; fundamentals freshness (450/550/730-day steps) is unchanged. | A price that turned 3.01 days old cut the multiplier by 0.105 (Equinor confidence 0.552 → ~0.49). | **yes** for the conservative engine if v2 is activated | v2 only |
| 2026-11-02 | P1.1 display | `v2` messages show confidence with 3 decimals, and with enough extra decimals that a value below the threshold never prints equal to it; the app shows confidence with 3 decimals instead of a rounded percentage (all versions: display only). The comparison operators were already on unrounded values. | "confidence 0.55 below accept threshold 0.55" was display rounding. | no (text only) | v2 messages; app any |
| 2026-11-02 | P1.3 additions (owner, 2026-11-02) | `v2`, both engines: (a) cross-dimension opposition (e.g. fundamental positive, forecast negative) never blocks; it is shown as an informational note (`agentNotes` on `/analyze`, flag `dimension_note` in the investment decision) and in the stock-detail UI; (b) a risk agent at vote ≤ −0.70 with confidence ≥ 0.65 caps the tier instead of a REVIEW: investment mode BUY → ACCUMULATE (flag `risk_cap`), conservative engine BUY_CANDIDATE → HOLD_OR_WATCH (`riskCap` field; the conservative vocabulary has no ACCUMULATE). The investment mode's own disagreement downgrade (`agents_disagree`) now follows the same-dimension rule in v2. Confidence 0.65 for "high" is my choice (the core risk agent emits 0.23–0.82); owner to confirm. | A quality company can be volatile (SAP); an extreme risk reading still must limit the rating. | **yes** (investment-mode v2 differs from v1; v1, which the paper measures, is untouched) | v2 only |
| 2026-11-02 | Portfolio | `v2`: `POST /global/portfolio` builds the portfolio from investment-mode tiers BUY and ACCUMULATE, ranked by investment score and confidence (confidence floor 0.35 kept, the conservative 0.15 score floor not applied). The conservative engine is the risk filter: a stock is excluded when evidence is not PASS, the conservative preliminary call is AVOID_OR_REVIEW, or Agent 9 sets a distress positive_block; scope, FX and price gates unchanged. Response `engine` = Investment ranking with `riskFilter: conservative`. | The conservative engine is almost always empty, so users saw an empty portfolio. | **yes** for the portfolio feature (not a paper measure) | v2 only |
| 2026-11-02 | P1.4 | `v2`: in `freshness.filing_dimension`, peers whose newest report may have been superseded (open quarterly window, known newer filing) or that have no filing date are no longer excluded from the peer benchmark; they stay with their latest available report. Benchmark freshness factor = 1 − 0.30 × (share of such peers); the comparison agent's confidence = 0.65 × factor (0.65 when none). Hard exclusions (explicitly excluded peers, inputs older than the ceiling) still count towards the 15 % limit, which is unchanged. v2 comparison-agent message names the real cause ("peer benchmark not trusted: …") and prints "fewer than 3 same-sector peers" only when that is true. 0.30 is my choice; owner to confirm. Effect on the real caches (read-only run 2026-11-02): SAP gets sector P/E 24.52, vote −0.5 (40 % premium), confidence 0.507 instead of abstaining; Equinor and Aker BP stay without a benchmark because the **quote** dimension fails (Euronext Oslo screening rows have no quote date, `quotesAsOf` is null for all 144 peers), see plan P2.4. | The comparison agent abstained for SAP (73 % undated peers) and the Oslo names (quarterly window) although 12 / 11 same-sector peers with a valid P/E exist. | **yes** for the conservative engine if v2 is activated (the comparison agent now votes, which moves score and BUY rules); the investment mode has its own peer logic and is unchanged | v2 only |

## Investigated, not a logic change

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
