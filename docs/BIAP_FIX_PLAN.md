# BIAP Fix Plan — for Claude Code

Compiled 2 Nov 2026 from live app testing. Covered: BIAP Global (Germany: SAP plus the full Xetra funnel; Norway: Aker BP, Equinor plus the Oslo funnel), ChatGPT's 1 Nov monitoring report, and the Iranian BIAP (Taban, Pekarman).

**Order of work (owner's decision):**
1. Fix BIAP Global for all current markets (10–12).
2. Test the remaining countries the same way and fix them.
3. Apply the planned app changes (new modules).
4. Re-run the accuracy tests.
5. Only then: startup applications (Estonia, Portugal, Lithuania).

Current markets: US, UK, IT, SE, NO, DE, FR, NL, FI, ES (+ DK, PT being added).

---

## Phase 0 — Housekeeping (do first)

- [~] **Finish PR #74 first.** *(2026-11-02: reviewed, all tests pass, mergeable; NOT merged, awaiting owner approval)* ChatGPT is working on branch `feat/mobile-checkpoint-staging-20261101` (PR #74: per-market broker selection, Checkpoint 1). Merge or close it before starting, so the two tools don't conflict on the same code.
- [x] Work on a new branch (`fix/biap-fix-plan-20261102`). Write a short changelog entry for every change to the decision logic.
- [~] **OSF protocol (osf.io/6p8y7, registered 22 Oct 2026).** Any change to gates or thresholds made after 22 Oct must be logged as a *protocol deviation*, with date and reason. This is required for the "From Abstention to Action" paper.
- [x] **Explain the BLOCK drop.** *(2026-11-02: cause = first full price-refresh run, not a gate change; see docs/CHANGELOG_DECISION_LOGIC.md)* BLOCK fell from ~4,750 to ~1,228 between 28 and 29 Oct. Find the cause and document it. If it came from a code or gate change, it is a protocol deviation (see previous item).

---

## Phase 1 — BIAP Global: decision layer (highest impact)

Evidence: Norway's data is healthy (only 23 of 134 rejected at the ranking standard), yet 94 of 111 ranked stocks end as NO_RECOMMENDATION. The bottleneck is here.

- [ ] **P1.1 Agent 8 threshold bug.** Equinor shows "calibrated confidence 0.55 below accept threshold 0.55". Aker BP was accepted at 0.56.
  - Compare unrounded values with a consistent operator.
  - Display 3 decimals. *(Done 2026-11-02: 3-decimal confidence in messages (v2) and in the app; the comparison itself was already on unrounded values, see `docs/reference_NO_before.md`.)*
  - Many Norwegian stocks sit at 0.50–0.57 confidence, so this likely explains a large share of the 94 NO_RECs.
- [ ] **P1.2 Do not confidence-gate neutral calls.** Low confidence should block only active calls (BUY/SELL). Score ≈ 0 must still map to HOLD (example: Equinor at 0.043 → HOLD, not NO_REC).
- [x] **P1.3 Agent 8 disagreement rule** *(v2, 2026-11-02: same-dimension rule implemented behind `DECISION_LOGIC_VERSION=v2`; the reviewer workflow for REVIEW is still open)*. SAP was escalated to REVIEW for "high-confidence disagreement": Quality +1 vs Risk −0.5. These agents measure different dimensions, and a quality company can also be volatile.
  - Fire the rule only between agents on the *same* dimension (e.g. Fundamental vs Forecast direction), or only when the signed contributions straddle a decision boundary.
  - REVIEW must have a real reviewer workflow. Otherwise stocks stay stuck forever.
- [~] **P1.4 Comparison Agent: peer-benchmark validity and misleading message** *(2026-11-02: filing-dimension discount and message implemented behind v2; Oslo still blocked by the missing peer quote date, see P2.4; awaiting owner approval)* *(revised 2026-11-02 after the SAP and Norway reference reads; the original "sector mapping bug" diagnosis was wrong for these three stocks)*.
  - Sector classification is correct: Equinor and Aker BP are both ICB "Energy / Oil, Gas and Coal" (60101000 / 60101010); 11 other Oslo energy names have a valid P/E; SAP has 12 Technology peers with valid P/E.
  - Real cause: `freshness.evaluate` marks the whole peer benchmark unusable (`peer_scan_cache_state = scan_cache_stale`, so `sector_pe` stays empty). DE/SAP: 73 % of peers are `filing_undated` (limit 15 %). NO: 100 % of peers are `filing_may_have_changed` because the quarterly reporting-calendar window (period end + 20 d … + 60 d) is open, although BIAP only ingests annual reports.
  - Fix the validity model, not the sector map (owner's decision 2026-11-02): peers are not dropped wholesale when a quarterly reporting window opens. Ingest interim reports (P2.3) and, until a peer's interim report is available, **use the peer's latest available report with a partial freshness discount** instead of excluding it. Peer rows without a filing date (DE) get their date from the reviewed/Börse Frankfurt record. Log any change to the 15 % limit or to the exclusion rule as a decision-logic change (the benchmark feeds `sector_pe`).
  - Fix the message in `core_agents.py` (`comparison_agent`): "fewer than 3 same-sector peers" must only appear when that is true. Otherwise say why (e.g. "peer benchmark not trusted: 73 % of peer filings undated" / "…filing window open").
  - If the benchmark is genuinely unusable, widen peers (European/all-market same sector), then sector-index median; exclude P/E outliers (> 100) from the median rather than from the peer count.
- [ ] **P1.5 Abstention fallback.** When only the Comparison agent abstains and the score is positive with PASS evidence, issue a capped tier (e.g. ACCUMULATE, "relative valuation unverified") instead of NO_RECOMMENDATION.
- [ ] **P1.6 "If already owned" must never be "No Action".** Give a hold-type tier.
- [ ] **P1.7 BUY threshold calibration.**
  - Scores are compressed: Germany's maximum is 0.250 and its average 0.039. The Iranian app shows the same ±0.27 clustering.
  - Calibrate the BUY/ACCUMULATE thresholds to the real score distribution (e.g. percentile-based within PASS and sufficient-confidence stocks), or rescale scores so they use the full −1…+1 range.
  - Check that abstaining or near-zero agents are not diluting the weighted average.
- [ ] **P1.8 Agent 9 and Agent 10 consistency.**
  - Aker BP shows "High Risk" with the positive-decision safety gate active. The trigger is Altman Z'' 1.06, while Zmijewski says distress-unlikely and Agent 10 rates A (PD 0.05%).
  - Altman Z'' is unsuitable for capital-intensive sectors (oil & gas, utilities, shipping). Altman alone must not trigger the safety gate there.
  - When the models disagree, show which result governs and why.
- [ ] **P1.9 Show the blocking gate.** Each stock's detail page *and* list row should state which gate blocked the call (e.g. "Agent 8 confidence", "comparison abstained", "BUY threshold").

- [x] **P1.10 Abstaining agents get no weight.** An agent that abstains (no vote; today confidence 0.25 or 0.0 with vote 0) must not take part in the weighting of the final score. Re-normalise the weights over the active agents only. Reference: SAP's abstaining comparison agent holds 6.7 % of the weight and pulls 0.2105 down to 0.1927. Implemented 2026-11-02 behind `DECISION_LOGIC_VERSION=v2` (v1 untouched; the investment mode already drops agents below 0.30 and is unchanged). Logged in `docs/CHANGELOG_DECISION_LOGIC.md`.
- [x] **P1.11 Two engines: make it explicit on every screen.** The system has a conservative engine (absolute thresholds, Agent 8 governance, `call`) and the investment mode (rank-based tiers). Document which engine each screen shows (see `docs/reference_NO_before.md`, section "Engines per screen") and label it in the UI (e.g. "Conservative check" vs "Investment ranking"), including which score/confidence number is shown. State in the methodology which engine the paper (From Abstention to Action) measures.

---

## Phase 2 — BIAP Global: data layer

- [ ] **P2.1 German fundamentals adapter (biggest data loss).**
  - Xetra: 340 of 373 PASS stocks are rejected at `ranking_evidence_standard` (core statements incomplete or coverage below 60%). That is 91%.
  - Norway loses only 17% at the same gate.
  - Fix statement parsing for German issuers.
- [ ] **P2.2 Parser gaps (even for large caps).**
  - SAP: interest expense, FFO and dividend are missing. **Interest expense: use "interest paid" from the cash-flow statement or the notes instead of the face "Finance costs" line** (the DE reviewed record rejects Finance costs because it mixes non-interest items; `esef.py` already reads `interest_paid` for FFO). Add FFO and dividend per share to the DE reviewed-record schema (`_ALLOWED_FIELDS`).
  - Equinor (verified 2026-11-02 against the public ESEF package, see `docs/reference_NO_before.md` §3): the parser reads only `ifrs-full:CurrentAssets` / `CurrentLiabilities`, but Equinor tags the subtotals `ifrs-full:CurrentAssetsOtherThanAssetsOrDisposalGroupsClassifiedAsHeldForSaleOrAsHeldForDistributionToOwners` and `ifrs-full:CurrentLiabilitiesOtherThanLiabilitiesIncludedInDisposalGroupsClassifiedAsHeldForSale` (accept these as fallbacks when no held-for-sale group exists). EBITDA stays unavailable because only impairment-inclusive D&A is tagged (keep refusing to guess; consider the cash-flow D&A note instead). Dividend per share exists in the package (`ifrs-full:DividendsRecognisedAsDistributionsToOwnersPerShare`, `…DividendsProposedOrDeclaredBeforeFinancialStatementsAuthorisedForIssue…PerShare`) but the ESEF parser has no dividend extraction for any issuer (Aker BP is missing it too). Market cap, P/B and EV/EBITDA are missing for both because `shares_outstanding` is not tagged and the Brreg supplement did not fill it.
  - **`esef.py` / `oam_esef.py` work items (owner, 2026-11-02):** (1) read dividend per share (`ifrs-full:DividendsRecognisedAsDistributionsToOwnersPerShare`, and the declared-but-not-recognised `…DividendsProposedOrDeclaredBefore…PerShare`) for every ESEF issuer; (2) accept the alternative current-asset / current-liability concept names (`ifrs-full:CurrentAssetsOtherThanAssetsOrDisposalGroupsClassifiedAsHeldForSaleOrAsHeldForDistributionToOwners`, `ifrs-full:CurrentLiabilitiesOtherThanLiabilitiesIncludedInDisposalGroupsClassifiedAsHeldForSale`) as fallbacks when `CurrentAssets` / `CurrentLiabilities` are not tagged and there is no held-for-sale group; (3) keep refusing impairment-inclusive D&A for EBITDA. Tests first, on the Equinor package facts.
  - Compute what can be derived: book value/share, P/B, market cap (shares × price), beta (vs DAX / OBX / local index).
- [ ] **P2.3 Fundamentals freshness.**
  - Only the 2025 annual report (305 days old) is used.
  - Ingest interim/quarterly reports.
  - Freshness must reflect the age of the fundamentals, not just the price: today freshness=1.00 while the fundamentals are 305 days old.
  - `auditStatus=unknown` is shown for audited annual reports. Set it from the source.
- [ ] **P2.4 Price pipeline** (from ChatGPT's 1 Nov report and the app):
  - **Euronext Oslo peer quote date (found 2026-11-02):** all 144 rows of the Oslo scan cache have `screening.quoteDate = null` and no `price_observed_at`, so the benchmark block's `quotesAsOf` is null and `freshness.evaluate` can never mark the quote dimension VALID. Equinor and Aker BP therefore stay without a peer benchmark even after P1.4 (v2). Needs a verified, dated quote source for Euronext Oslo (do not stamp a session date without proof). Check the other Euronext markets the same way (DE has `quotesAsOf` 2026-10-29).
  - The EU refresh service failed on 30 Oct because Milan hit its deadline after 12 of 193 companies, yet 10 of 11 markets had completed. Run each market as an isolated job (or record per-market status), and give Milan more time or batching.
  - 3,001 NASDAQ records are dated Saturday 31 Oct with unchanged prices. Use an exchange trading calendar and stamp the last trading day.
  - Prices are stamped `08:00 UTC` (opening snapshot) in DE and NO. Use the official close.
  - 345 Xetra prices changed (30→31 Oct) without re-analysis. If the price is newer than the analysis, re-run it or flag it "analysis stale".
  - 1,273 records use sync-derived dates instead of verified trading dates.
  - "Global Top 10" shows "Partial global scan • 1/9 markets ready", so the global shortlist is effectively unavailable. Fix after the EU refresh is fixed.
- [ ] **P2.5 Currency labels.** Aker BP and Equinor report in USD while prices are in NOK. Label the fundamentals table and EPS with the reporting currency (P/E conversion is already correct).
- [ ] **P2.6 Data licensing.** The price source is "Yahoo · Public market history" (quality 0.72), which is not licensed for commercial use. Plan a licensed market-data provider before selling subscriptions, and add its cost to the business plan.

---

## Phase 3 — BIAP Global: UI and wording

- [ ] Show which stocks the Evidence gate passed and which the statement-completeness gate rejected. Both are currently called "evidence", which conflicts: "PASS 373" vs "insufficient evidence 374". Rename the second one, e.g. "statement completeness".
- [ ] Price Intelligence says "insufficient verified P/E" even when P/E exists. Change it to "peer benchmark unavailable".
- [ ] "A low share price alone does not mean undervalued" shows for €211 / NOK 447 stocks. Make it conditional.
- [ ] "Highest-ranked in this scan: —" is blank in DE and NO although #1 exists.
- [ ] Lists are sorted by score × confidence (correct). Show the sort key.
- [ ] SAP shows 0.191 on the detail page and 0.193 in the list. Use one scan, or show the scan time.
- [ ] **Three different scores for one stock (0.191 / 0.193 / 0.213).** Detail page = fresh `POST /global/analyze` (conservative score), list = stored ledger score (0.192688), investment ranking = 0.212994. Show one primary score per screen, name the engine and show the analysis time (see P1.11).
- [ ] Score displays "-0" (Aker BP). Format as 0.00x.
- [ ] Label "144/145 screened (price data only)" conflicts with "144 deep-analyzed".
- [ ] Clarify D/E (financial debt) vs liabilities/equity (total liabilities) labels.
- [ ] Portfolio Agent returns empty when there are 0 BUYs. Allow ACCUMULATE/HOLD or show the nearest candidates.

---

## Phase 4 — Validate every market

After Phases 1–3, run each market and record its rejection funnel: discovered → analyzed → evidence PASS → statement standard → ranked → tiers.

Acceptance criteria per market:
- No "x below threshold x" messages.
- The Comparison agent is active (not abstaining) for most ranked stocks.
- Price date = last trading-day close.
- The funnel shows where and why stocks drop.
- Markets with healthy data produce a plausible spread of BUY/ACCUMULATE/HOLD/REDUCE/SELL, or a documented reason why not.

Do this first for the 10–12 current markets, then for each remaining country as it is added. Keep before/after funnels: they are a figure for the paper.

---

## Phase 5 — Iranian BIAP (do not submit anywhere until fixed)

**Data (root cause of the empty pages):**
- [ ] Set the **Tindex production token** on the server (the Data Connections page says "Tindex: production token not available"). Resume enrichment: only 3,285 of 7,182 companies are enriched. The 300/day free cap and earlier server overload apply.
- [ ] Build or repair the **CODAL financial-statement connector** (revenue, cost of sales, net profit, margins).
- [ ] Wire **Kiasha's fundamental agent, the KPI module and the Financial Model** to the same stored data. Today KPI says revenue/cost are AUTO from CODAL while Kiasha says CODAL data is awaited and gives fundamentals a 0% weight.
- [ ] Until CODAL works, let the fundamental agent use TSETMC EPS/P/E as partial input.
- [ ] Pekarman's price is STALE. None of the three tested Iranian companies has usable statements in the DB (ChatGPT report).

**Bugs:**
- [ ] Taban 60-day trend shows +2175% (percent ×100 bug; real value ≈ 21.75%).
- [ ] Taban market cap shows 6,438,000 billion rial, probably 1000× too big.
- [ ] Market ID shown instead of symbol/company name when the name is missing (Taban header, Financial Model card "23214828924506640", some registry rows). Add a name fallback.
- [ ] Unlabeled row "9.08" on the Taban page.
- [ ] "Sell"/"Buy" badge shown while DATA HOLD says no recommendation. Show "Hold / insufficient data" instead.
- [ ] Negative final score vs all-positive scenarios. Reconcile, or explain that scenarios use 90-day memory and the score uses the recent trend.
- [ ] Confidence is 30% with 5 observations and also with 37. Confidence must scale with sample size.
- [ ] "BIAP memory 90d +12.4%" conflicts with 3m momentum +65.8%. Label memory as sparse observations, or use the full price history.
- [ ] Agent weights sum to 101% / 99%. Normalise the display to 100%.
- [ ] Green "خریدم – شروع پیگیری" button sits under a Sell signal. Make it neutral: "ثبت در پرتفوی من".
- [ ] Add a "صف خرید/فروش" badge when the day's range is a single price at the limit.
- [ ] Check that 52-week ranges and history are adjusted for capital increases.
- [ ] The sample CSV text (1404-10 revenue 1,000,000…) must only ever be a placeholder.

---

## Phase 6 — Planned app changes (new features)

- [ ] **AI Accounting with SAF-T 1.40** (mandatory in Norway from 1 Jan 2027; B2B e-invoicing from 2027). Do this first.
- [ ] **AI Audit** and **AI Analysis** modules in the "More" menu (company analysis and audit analysis).
- [ ] **Investments:**
  - Ratings uniform for all users.
  - Methodology page with the analyst's name.
  - Archive of past ratings.
  - Links to licensed brokers (no order execution).
  - Reduce Portfolio personalisation (avoid personal investment advice).
- [ ] Companies section: three sustainability agents (**MIA, PTA, ECA/ESG**) plus the **risk-assessment agent**, for business users.
- [ ] Broker API connection stays "SOON" and only via licensed brokers. Never send orders from BIAP.

---

## Phase 7 — Before the startup applications

- [ ] Re-run the accuracy tests on the fixed system. Update the numbers in the proposal and pitch deck.
- [ ] Take fresh screenshots of BIAP Global for the pitch deck.
- [ ] Then fill in Estonia (Startup Includer), Portugal (IAPMEI StartUP Visa) and Lithuania.
