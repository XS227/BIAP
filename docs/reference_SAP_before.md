# Reference stock: SAP SE (XETRA) — state BEFORE any fix

Compiled 2026-11-02 for `docs/BIAP_FIX_PLAN.md`, Phase 0. **Read-only**: nothing was changed on the server, the
database or the code. Purpose: a "before" baseline to compare against after Phases 1–3.

## Sources and how to reproduce

| What | Where |
|---|---|
| Stored analysis (ledger row, 29.9 KB JSON, zlib) | `/var/lib/biap-global/analysis-ledger/DE__XETRA.sqlite3`, table `ledger`, ticker `SAP`, `analyzed_at = 2026-10-30T18:10:28Z`. Read from a **copy** of the file (WAL mode needs write access to the live `-shm`). |
| Investment-mode tier | `GET http://127.0.0.1:8091/global/recommendations?country=DE&exchange=XETRA&limit=500` (read-only GET) |
| Peer benchmark cache | `/var/lib/biap-global/scan-cache/DE/XETRA.json` (cachedAt 2026-11-01T11:32Z) |
| Code | live checkout `/home/ubuntu/biap-global/BIAP` @ `6c8ada1` (service pid 896). `analysis/global_markets` is byte-identical to `origin/main` @ `ee287e4` except `broker_catalog.py`, so every file/line reference below also holds on the fix branch. |

Not run: a live `POST /global/analyze` for SAP (it fetches external data and may write caches). This matters for
item 7 (0.191 vs 0.193) — see there.

## 1. Score, confidence and weight of the six factors

Aggregate = confidence-weighted mean of the votes: `Σ(vote·conf) / Σconf` (`service.py:76 _weighted_score`).
The "weight" of an agent is therefore its **confidence share**, not a fixed table. Σconf = 3.71.

| Agent | Vote | Confidence | Weight | Contribution | Reasoning (stored) |
|---|---:|---:|---:|---:|---|
| fundamental | +0.15 | 0.71 | 19.1 % | +0.0287 | revenue +7.7 % YoY; positive operating and free cash flow |
| risk | −0.50 | 0.78 | 21.0 % | −0.1051 | max drawdown −43.0 %; volatility 41.3 %; liabilities/equity 0.56x; current ratio 1.16x |
| forecast | +0.30 | 0.69 | 18.6 % | +0.0558 | 1m +13.1 %, 3m +26.2 %, 6m +39.5 %; 52w range position 81 % |
| comparison | 0.00 | 0.25 | 6.7 % | 0.0000 | P/E 34.41; sector peer P/E unavailable; **abstaining** |
| quality | +1.00 | 0.74 | 19.9 % | +0.1995 | net margin 19.9 %; OCF/NI 1.25x; ROA 10.4 % |
| liquidity | +0.12 | 0.54 | 14.6 % | +0.0175 | turnover 0.158 % of market cap/day |

- `rawScore` = **0.196307** → × evidence multiplier 0.981563 → `score` = **0.192688**.
- decision confidence = Σconf/6 = 0.618333 → × 0.981563 → overall calibrated confidence = **0.606933**.
- The abstaining comparison agent (vote 0, conf 0.25) still gets 6.7 % weight and pulls the score towards zero
  (without it the score would be 0.2105). This is P1.7's "abstaining agents dilute the average".

## 2. Exact reason for NO_RECOMMENDATION

Not a confidence gate and not a score gate. The path (`service.py:753 _analysis_payload`, `governance.py`):

1. `_call()` (`service.py:645`): score 0.1927 < 0.25 → preliminary call **HOLD_OR_WATCH** (`decisionIntegrity.preliminaryCall`).
2. Agent 8 governance: `evidence.contradictions` is non-empty → `governance.py:83` returns
   `action=REVIEW, final_call=NO_RECOMMENDATION` ("Escalated to human review: high-confidence agent disagreement").
   This branch runs **before** the confidence test, and it also overrides a HOLD (P1.2 in the plan).
3. Confidence 0.607 is above the 0.55 accept threshold, so no threshold is involved. Evidence gate = **PASS**
   (coverage 100 %, freshness 1.00, source quality 0.93, provenance independently_verified, audit audited).
4. Distress gate: LOW_RISK, `positive_block=false` — not involved.

`decisionReasons.governance[0]`: `AGENT_DISAGREEMENT … blocksDecision: true`. `opportunity.state = REVIEW`,
`primaryCause = GOVERNANCE_RESTRICTION`.

## 3. Agent 8 disagreement rule (exact condition)

`agents.py:262-277` (inside `evidence_agent`): over all signals with **confidence ≥ 0.55**, collect
`vote ≥ +0.35` as confident-positive and `vote ≤ −0.35` as confident-negative; if both lists are non-empty →
contradiction. There is no notion of dimension: any agent against any agent.

SAP: positive = {quality +1.00 @0.74}, negative = {risk −0.50 @0.78} → fires. Consequence in the conservative engine:
`governance.py:83` → REVIEW → NO_RECOMMENDATION. There is no reviewer workflow behind REVIEW (no code path
resolves it), so the state is permanent until the inputs change.

The investment mode has its own copy of the rule (`investment_mode.py has_disagreement`, same 0.55 / ±0.35).
There it only **downgrades one tier**; for SAP it fired between quality (+1.0) and comparison (−0.5).

## 4. Industry and the peer list the comparison agent found

- Classification: sector **Technology**, industry "Software - Software" (source: Deutsche Börse Listed-companies file,
  translated to ICB; `sector_kind=operating`).
- The conservative comparison agent (`core_agents.py:298`) needs `company.sector_pe`. That is filled in
  `service.py:463` from `_peer_pe_benchmark` (≥3 same-sector peers with 0<P/E<500 from the persisted scan).
- **At analysis time it found no peers at all, but not because there are fewer than 3.**
  `raw_provider_fields.peer_scan_cache_state = "scan_cache_stale"`: the whole benchmark was discarded by the freshness
  model (`service.py:124 _peer_benchmark_info` → `freshness.evaluate`) because the *filing* dimension is
  `UNDETERMINED`: **102 of 139 peers (73.4 %) are `filing_undated`**, limit is 15 %. The same verdict holds today
  (re-evaluated on the 2026-11-01 11:32Z cache: usable = False).
- The message "fewer than 3 same-sector peers with a valid P/E" (`core_agents.py:316`) is printed whenever `sector_pe`
  is empty, whatever the cause — so it is misleading here.
- The cache itself contains 14 other Technology peers; 12 have a valid P/E:
  IXX 21.07, YSN 47.18, SHF 17.82, IVU 27.87, 1GBS 8.42, AOF 37.96, 1INN 21.20, NEM 49.36, TMV 8.40, GFT 15.15,
  LSX 27.85, RTC 94.00 (CHG −33.47 and C3R none excluded). Median 24.5 → SAP (34.4) would be ~40 % at a premium.
  I did not compute what the agent would then vote; that needs the full benchmark path.
- So for SAP the plan's P1.4 "sector mapping" diagnosis is **not** the cause; the cause is the peer-benchmark freshness gate
  (undated peer filings). Sector mapping is a separate matter for Equinor/Aker BP and was not checked here.
- Investment mode does not use `sector_pe`: it uses `peerScope = exchange_sector` and gives comparison **−0.5**.

## 5. Why interest expense, FFO and dividend are empty

- **Interest expense**: deliberately not taken. The reviewed-report record for SAP
  (`analysis/global_markets/data/de_verified_annual_reports.json`) says: "interest_expense not taken: face 'Finance costs'
  mixes non-interest items." → Agent 9 reports `interest_coverage = null`, `missing_inputs = [interest_coverage:interest_expense]`.
- **FFO**: the DE reviewed-report schema cannot hold it. `_ALLOWED_FIELDS` in `german_reviewed_reports.py:29` has no
  `ffo`. FFO is only derived in `esef.py:1090` from ESEF cash-flow facts (interest paid, taxes paid), and SAP has no
  ESEF package in BIAP's registry (`fundamentals_primary_error: "no reviewed issuer-published ESEF package for DE0007164600"`).
- **Dividend**: same cause — `dividend_per_share` is not an allowed field in the German reviewed record, and the
  Börse Frankfurt supplement only fills the share count (`de_share_count_supplement`). `dividend_yield_pct` is derived
  only when a DPS exists (`service.py` ~441), so it stays null; `decisionTable.incomeProfile = INSUFFICIENT_DATA`.
- All three are known data gaps (not zero); the data came from SAP's own integrated-report workbook (FY2025, period end
  2025-12-31, 303 days old at analysis time, tier LAST_ANNUAL_FILING). No interim report is ingested.

## 6. Why the price time is 08:00 UTC

- The deep-analysis price comes from `yahoo-public-chart-global` (symbol `SAP.DE`), a *secondary public EOD source*
  (source quality 0.72, "used only because no licensed market feed is configured").
- `price_observed_at = 2026-10-30T08:00:00+00:00` is simply the **timestamp of Yahoo's daily bar**
  (`yahoo_chart.py:159 _observed_at` converts the bar's epoch to ISO; `:253`). Yahoo stamps a daily bar with the session
  *start*; XETRA opens 09:00 CET = 08:00 UTC after the clock change (25 Oct). It is not the time of the closing price.
  `latest_bar_partial_session = false`, so the stored value is the bar's close, but the label says "open".
- Two other quotes sit in the same record: the official Xetra post-trade file of **2026-10-29** (208.85, stage-1
  screening, `observed_at 2026-10-29T00:00:00Z`) and `decisionTable.metrics.price` 211.25. Three prices, two dates.

## 7. 0.191 versus 0.193

- Both the ledger row (list) and the scan cache hold **0.192688 → "0.193"** at 3 decimals. I could not find 0.191 in any
  stored data; `analysis_history` is empty for SAP.
- The detail page does not read the ledger: `mobile-global/src/app/stock/[code].tsx:138` calls
  `analyzeGlobalInstrument` → `POST /global/analyze`, i.e. a **fresh re-analysis** with a fresh Yahoo fetch (new price,
  returns, volatility, volume), while the list shows the stored 2026-10-30 18:10Z result. A fresh run on a later day gives a
  slightly different forecast/risk/liquidity vote → a slightly different score. This is the most likely cause
  (**not verified by a live run**).
- There is a **third** SAP number: investment-mode score **0.212994** (ranking engine, different risk vote). So the app
  can show 0.191 / 0.193 / 0.213 for the same stock on the same day.

## 8. Thresholds in code

Conservative engine (`service.py:640-652 _call`, evidence `agents.py`, governance `governance.py`):

| Rule | Value |
|---|---|
| NO_RECOMMENDATION if evidence BLOCK or confidence | < 0.35 |
| BUY_CANDIDATE | score ≥ 0.25 **and** confidence ≥ 0.45 **and** evidence PASS (and no distress block) |
| AVOID_OR_REVIEW | score ≤ −0.25 and confidence ≥ 0.45 |
| otherwise | HOLD_OR_WATCH |
| Agent 8 accept / escalate | confidence ≥ 0.55 accept; 0.35–0.55 REVIEW; < 0.35 ABSTAIN (`governance.py:28-29`) |
| Extra BUY review rules | distress LOW_RISK/NOT_APPLICABLE; peer group ≥ 8; not comparison-only |
| Disagreement | conf ≥ 0.55 and vote ≥ +0.35 vs ≤ −0.35 (any pair) → REVIEW |
| Evidence WARN | always REVIEW → NO_RECOMMENDATION |
| ACCUMULATE | **does not exist** in the conservative engine |

Investment mode (`investment_mode.py:82-123`, `InvestmentConfig`; live product, `DECISION_MODE=investment`):
BUY = top 10 % of the exchange with score > 0 and ≥ 4 agents; ACCUMULATE = top 25 % with score > 0;
REDUCE = bottom 25 % with score < 0; SELL = bottom 10 % with score < 0 and ≥ 4 agents; else HOLD.
`min_tier_confidence 0.35`, `data_min_confidence 0.30`, disagreement downgrades BUY→ACCUMULATE.
**There is no absolute score floor** (the 0.10 floor was removed 2026-10-19), so the tiers are purely rank-based.

SAP in investment mode (live API, 2026-11-02): **ACCUMULATE**, score 0.212994, confidence 0.67237, rank 39 of 391,
percentile 9.69 % (inside the top 10 %), flags `agents_disagree`, `peer_scope_exchange_sector`. It would have been BUY
but the disagreement downgrade moved it one tier. Tier counts for XETRA: BUY 25, ACCUMULATE 66, HOLD 202, REDUCE 60,
SELL 38, NO_RECOMMENDATION 16 (total 407, 391 ranked).

## Summary of the SAP "before" state

| Item | Value |
|---|---|
| Conservative call | NO_RECOMMENDATION (preliminary HOLD_OR_WATCH, Agent 8 REVIEW) |
| Conservative score / confidence | 0.192688 / 0.606933 |
| Blocking gate | Agent 8 disagreement (quality +1.0 vs risk −0.5), not a threshold |
| Evidence / distress | PASS / LOW_RISK (Zmijewski 6.2 %, Altman Z″ 5.25 safe) |
| Investment-mode tier | ACCUMULATE (0.212994 / 0.672, rank 39) |
| Comparison agent | abstained — peer benchmark discarded (73 % undated peer filings), message misleading |
| Missing fundamentals | interest expense (deliberate), FFO, dividend (schema/ESEF gaps) |
| Fundamentals age | 303 days (FY2025 annual only) |
| Price | 211.25 EUR, stamped 2026-10-30T08:00Z = Yahoo daily-bar start; official Xetra quote 208.85 dated 10-29 also in record |
