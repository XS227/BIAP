# Reference stocks: Equinor and Aker BP (Euronext Oslo) — state BEFORE any fix

Compiled 2026-11-02, Phase 0, **read-only** (ledger read from a copy; no server, database or code change).
Companion to `docs/reference_SAP_before.md`. Code references are to `analysis/global_markets` (live checkout `6c8ada1`,
identical in the decision engine to the fix branch base `live/base-20261030`).

Data: `/var/lib/biap-global/analysis-ledger/NO__EURONEXT_OSLO.sqlite3` (rows analysed 2026-11-01T21:42Z),
`/var/lib/biap-global/scan-cache/NO/EURONEXT_OSLO.json` (cachedAt 2026-11-01T21:40Z), daily snapshots 20 Oct – 1 Nov.

## 0. Stored state (conservative engine)

| | Equinor (EQNR) | Aker BP (AKRBP) |
|---|---|---|
| Call | HOLD_OR_WATCH, Agent 8 **ACCEPT** | HOLD_OR_WATCH, Agent 8 **ACCEPT** |
| Score (raw → final) | 0.045389 → **0.043304** | −0.000420 → **−0.000401** |
| Decision confidence × evidence multiplier | 0.578333 × 0.954063 = **0.551766** | 0.595000 × 0.954063 = **0.567667** |
| Evidence | PASS (coverage 93.75 %, freshness 1.00) | PASS |
| Distress (Agent 9) | INSUFFICIENT_DATA (only interest coverage 17.65x) | **HIGH_RISK**, `positive_block = true` |
| Price | 447.5 NOK, 2026-10-30T08:00Z (Yahoo bar start) | 392.3 NOK, same |
| Fundamentals | FY2025 annual, 305 days old, reported in **USD** | same |

Agent table (vote / confidence / weight = confidence share):

| Agent | EQNR | AKRBP |
|---|---|---|
| fundamental | −0.05 / 0.71 / 20.5 % | −0.35 / 0.71 / 19.9 % |
| risk | −0.30 / 0.68 / 19.6 % | −0.05 / 0.78 / 21.8 % |
| forecast | +0.20 / 0.69 / 19.9 % | +0.20 / 0.69 / 19.3 % |
| comparison | 0.00 / 0.25 / 7.2 % (abstains) | 0.00 / 0.25 / 7.0 % (abstains) |
| quality | +0.35 / 0.74 / 21.3 % | +0.20 / 0.74 / 20.7 % |
| liquidity | 0.00 / 0.40 / 11.5 % | 0.00 / 0.40 / 11.2 % |

The stored Equinor row therefore does **not** carry the "0.55 below 0.55" message; it was accepted. The message the app
showed must have come from a fresh analysis (the detail page calls `POST /global/analyze`), see question 1.

## 1. "Confidence 0.55 below accept threshold 0.55": rounding in the display, not in the comparison

- Exact stored number for Equinor: **0.551766** (≥ 0.55 → accepted). Aker BP: 0.567667, accepted at "0.57".
- Every comparison is on the **unrounded** float: `governance.py:136` `if conf >= accept_threshold` (REVIEW branch at `:146`
  `conf >= escalate_threshold`), `decision_reasons.py` `confidence < accept_threshold`, `opportunity.py` `confidence < 0.55`.
  Only the message text is formatted with `:.2f` (`governance.py:148`, `decision_reasons.py:61`, `opportunity.py:83`).
  So "0.55 below 0.55" means the real value was in **[0.545, 0.55)** and is a **display-rounding** problem. The comparison operator is correct.
- I cannot give the exact number the app showed: no stored result has it and I did not run a live analysis. Plausible mechanism:
  Equinor sits 0.0018 above the line. confidence = mean(agent confidences) × evidence multiplier, where the multiplier is
  `0.45·coverage + 0.30·freshness + 0.25·avg(source quality)` (`agents.py:298`). The average source quality (0.926) shifts
  whenever a source is added or dropped (e.g. one more Yahoo source at 0.72 or a cached source at 0.88), and a drop of ≈ 0.003 in the multiplier
  (to 0.951) is enough to fall below 0.55.
- The same fragility exists one step earlier: freshness is a step function (`agents.py:117`: price age ≤ 3 days → 1.0, ≤ 7 → 0.65, ≤ 30 → 0.25).
  A price older than 3 days would drop Equinor's multiplier by 0.105 → confidence ≈ 0.49.
- Equinor is also one rounding step from the disagreement rule: quality +0.35 (conf 0.74) is exactly on the +0.35 line, risk −0.30 is 0.05 away from −0.35.
  A small change in either vote would produce REVIEW → NO_RECOMMENDATION as for SAP.
- Why Equinor can land on NO_RECOMMENDATION with a HOLD draft at all: below 0.55 the conservative engine has no "accept a neutral call"
  path (P1.2 in the plan).

## 2. Why the comparison agent abstains: peer-benchmark freshness, not industry classification

- Classification is fine. Both are `sector = Energy`, `industry = Oil, Gas and Coal`, source Euronext ICB (`60101000` Equinor,
  `60101010` Aker BP; ISIN-exact match, retrieved 2026-10-13). The Oslo scan cache holds 25 Energy names; 11 *other* Energy names
  have a valid P/E (SOFF 3.97, BNOR 16.93, IWS 12.68, SOMA 5.85, VAR 18.35, AKSO 6.83, MGN 65.16, TGS 151.56, PNOR 22.09,
  REACH 17.68, HAVI 20.35). That is above the 3-peer minimum (`service.py:230`), so the "fewer than 3 same-sector peers" message
  (`core_agents.py:316`) is **wrong for both stocks**.
- Actual cause (both stocks, stored `raw_provider_fields`): `peer_scan_cache_state = "scan_cache_stale"`. The benchmark verdict
  from `freshness.evaluate` (`service.py:124 _peer_benchmark_info`): filing dimension **STALE, 100 % of peers (95/95)
  excluded, reason `filing_may_have_changed`**; limit is 15 % (`freshness.py:45`). When the benchmark is unusable, `sector_pe`
  stays empty and the agent abstains with the generic message.
- Why every peer is flagged: Norway is in the *quarterly* regime (`freshness.py:51-53`, cadence 92 days, deadline lag 45, earliest lag 20).
  `filing_may_have_changed` (`freshness.py:110`) asks whether a newer filing could have been published after the base scan.
  For period end 2025-12-31 the third interim window is ≈ 2026-10-23 … 2026-12-02, which is open now (today 2026-11-02),
  so every peer row is considered possibly superseded — although BIAP only ingests the **annual** report. This repeats every
  quarter for ≈ 40 days and rebuilding the base does not cure it before the window closes.
- Contrast with SAP: there the cause was `filing_undated` (73 % of DE peers have no filing date). Different trigger, same outcome and same misleading message.
- The 95 peers contain the 11 energy names above, so the investment mode (which uses its own peer logic, `peer_scope`) does compare
  them; the conservative engine does not.

## 3. Missing EBITDA, FFO, current assets/liabilities, dividend — Equinor vs Aker BP

Both come from the same official source and parser: Oslo NewsWeb OAM ESEF package (`official-oam-no-oslo-newsweb`, FY2025,
`oam_credit_extraction` in `raw_provider_fields`; `esef.py` / `oam_esef.py`). Per field:

| Field | Equinor | Aker BP | Reason |
|---|---|---|---|
| EBITDA | missing | 7.33 bn USD | Equinor tags D&A **together with impairments** only (`DepreciationAmortisationAndImpairmentLossReversalOf…` = 12.318 bn; `…Adjustments…` = 12.473 bn). The parser refuses to use impairment-inclusive D&A ("never guessed", `field_status: tagged_da_impairment_inclusive_only_not_used`). Aker BP has a plain D&A total (2.574 bn) → EBITDA = operating income + D&A. Using Equinor's figure would overstate D&A about fourfold relative to Aker BP's ratio. |
| FFO | missing | 3.88 bn USD | FFO = EBITDA − interest paid − taxes paid (`esef.py:1090`); without EBITDA it cannot be computed. Consequential, not a separate gap. |
| Current assets / liabilities | missing | 5.14 bn / 3.93 bn | The parser reads only the standard concepts `ifrs-full:CurrentAssets` / `ifrs-full:CurrentLiabilities` (`esef.py:78-79`). Equinor's package evidently does not carry them (no fallback exists). **Not verified**: the raw XBRL package is not kept on disk (only normalized `latest.json`), so I could not list Equinor's actual concept names. Verifying needs one download of `oam_package_url` (external request; your OK needed). Consequence: Zmijewski and Altman cannot run → Equinor distress = INSUFFICIENT_DATA. |
| Dividend per share / yield | missing | **also missing** | Correction to the plan: Aker BP does not have it either. The ESEF/OAM parser has no dividend extraction at all (`dividend_per_share` is only read in `sec_edgar.py` and `boerse_frankfurt_fundamentals.py`). |
| Market cap, P/B, EV/EBITDA | missing | **also missing** | Correction to the plan: both. `shares_outstanding` is `not_tagged_in_filing` for both and the Norwegian share-count supplement (`exchange_shares.py`, Brreg share capital) did not fill them; so market cap, book value per share, P/B and EV/EBITDA cannot be derived. |
| Interest expense | 1.436 bn USD (ICR 17.65x) | 0.0704 bn USD (ICR 67.6x) | read for both |

So the plan's statement "the same Oslo source parses these fine for Aker BP, so the Equinor report parser is at fault" is only partly right:
the cash-flow/EBITDA/current-items gaps are Equinor-specific tagging cases that the parser deliberately or structurally does not handle; the dividend and market-cap gaps affect both.

## 4. Other findings relevant to the plan

- **Aker BP "High Risk"**: Altman Z″ = 1.057 (distress zone) sets `positive_block = true`, while Zmijewski P = 0.488 is labelled "distress-unlikely"
  and Agent 10 gives an A-range rating; interest coverage 67.6x. No rule says which model governs (P1.8). The conservative call is HOLD, so the block did not change it here.
- **Reporting currency**: both report in USD, price in NOK; P/E is FX-converted correctly
  (`fx_converted:USD->NOK; balance_rate=10.0791@2025-12-31; flow_rate=10.3883`, ECB), fundamentals are shown in USD (P2.5).
- **Two confidence numbers**: daily snapshot (investment mode) shows EQNR confidence 0.61537 and score 0.01491 on 2026-11-01, the ledger (conservative) 0.551766 / 0.043304.
- **Snapshot history**: tier HOLD for both on every day 20 Oct – 1 Nov; EQNR/AKRBP were evidence BLOCK on the 27 Oct snapshot only (cleared by the 28 Oct re-analysis).

## 5. Engines per screen (P1.11) — from code reading, not from running the app

Backend: `GET /global/analyze|scan` = conservative engine (`service.analyze_company`, Agent 8 `call`); `GET /global/recommendations` and the
`investment` field added by `decision_overlay` = investment mode (live default, `DECISION_MODE=investment`, tiers BUY…SELL, rank-based).
`POST /global/portfolio` → `portfolio_from_instruments` → `portfolio_agent` = conservative scores (`min_score 0.15`, `min_confidence 0.35`), no investment tier.

| Screen (mobile-global) | Decision label shown | Score/confidence number shown |
|---|---|---|
| Stock detail (`stock/[code].tsx:138,263,269`) | investment tier if present (after `cap_for_evidence`), else conservative call | conservative **fresh** analysis (`analysis.score`, `analysis.confidence`) |
| Market list (`market.tsx:96,306,328`) | investment tier badge (`/global/recommendations`); scan rows use the row's `investment` | none / conservative scan rows |
| Kiasha (`kiasha.tsx:56,141`) | **both**: top picks from `scanGlobalMarket` recommendations (conservative, qualified BUY, usually empty) **and** a tier card from `/global/recommendations` (investment) | picks: conservative; tier card: investment confidence |
| Portfolio (`/global/portfolio`) | conservative path only (score ≥ 0.15) | conservative |

Consequence: one stock can carry three scores on one day (SAP 0.191 / 0.193 / 0.213) and a conservative NO_RECOMMENDATION next to an
investment ACCUMULATE. Not labelled in the UI today.

**Which engine the paper measures.** `research/papers/BIAP_Global_Chapter_4_Empirical_Results_2026-10-21.md`
studies the **investment mode** ("investment-mode-adjusted vote", 7,593 universe rows, 964 extreme-tier decisions = 445 BUY + 519 SELL, decision
engine commit `7c0606e`; `research/build_paper_portfolio.py` sets `DECISION_MODE=investment`; paper portfolio frozen 2026-10-20, tag
`paper-portfolio-2026-10-20`). It names abstention, disagreement and evidence caps as modifiers inside that engine. The conservative engine (the "abstention"
side of the title) appears only as the stored `conservativeCall` and in the classification census. I found no file titled "From Abstention to Action"
in the repository; this reading is from the Chapter 4 draft only, so please confirm that the paper text matches. Any change to P1.x logic in the
**investment** mode changes what the paper measures (protocol deviation); changes limited to the conservative engine do not alter the frozen paper portfolio
but do alter what users see.
