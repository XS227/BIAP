# GB / LSE — full-universe production evidence audit (2026-10-18)

Scope: UK (LSE Main Market) only. Nothing deployed or merged; gates, BUY logic and historical data untouched.
Evidence base: production API `127.0.0.1:8091` (service commit `2f661e6`), every instrument of the advertised GB/LSE catalog
(527 operating equities; 285 pooled investment vehicles and 120 non-ordinary lines are already excluded by the catalog),
`POST /global/analyze` per instrument via `tools/audit_global_evidence.py` (unchanged). Per-instrument ledger:
`docs/market-audit/research/2026-10-18/GB__LSE.audit.json`. For all 106 non-PASS rows the FCA NSM was queried by LEI (no tag filter)
to see what the official source really holds.

## Result (production, before)

| Metric | Value |
|---|---|
| Universe audited | 527 / 527 |
| Evidence PASS | **421** (79.9 %) |
| Evidence BLOCK | **105** |
| API failure | 1 (`1SN`) |
| Official class | OK 360 · SUSPECT_VALUES 61 (see note) · LEGIT_OFFICIAL_UNAVAILABLE 43 · INDEX_LAG 35 · PIPELINE_FAILURE 11 · COVERAGE_GAP 10 · LEGIT_OFFICIAL_STALE 6 · API_FAILURE 1 |

## Stratification of the 106 non-PASS rows (root cause from the NSM, not from BIAP's own classifier)

| # | Stratum | Tickers |
|---|---|---|
| 50 | Newer annual report exists on NSM only as PDF / RNS "Final Results" text (no inline XBRL) — **no machine-readable official source** | ALNA ALTR AMG AMOI BRES BYG CHF CHLL COBR DISH ECOR EDV ESNT EVST GEMR GR1T GSCU HEMO HUI IBAI IGG IHP KLSO KNB KR1 MAB1 MACF MILA NANO NARF NFX NXR OMU ONDO PAF PCA PHP PRE PTEC ROSE SRE THAL TNE UPL VALT VLX VP. WISE ZAIM ZEG |
| 18 | Newest annual report lodged "Untagged" (HTML/pdf2htmlEX) | AEWU AIC ALRT BSFA CABA CABB CABP CGEO CIZ CYKL EJFI EJFZ FWT HAN HANA HID HREE SIGC |
| 18 | GLEIF has no LEI for the ISIN (identity cannot be proven; mostly AIM / foreign ISINs) | AIRC AMRQ BVC DAT HAMA IMC KAKU NFM PYX RSG SEFA TKO UMR VOX WCAT WRN ZEN ZOYO |
| 7 | LEI known, nothing lodged on NSM | AMC DATA FDM GEX MNO MOH WGP |
| 5 | Latest tagged package is itself old/late and no newer filing exists yet | DVT EVR HELD IWG SYME |
| 2 | Fiscal transition > 12 months (annual scoring deliberately blocked) | AMGO (18 m) MCG (15 m) |
| 1 | Newest tagged package embeds another entity's LEI (hard gate) | MNTL |
| **5** | **Fixed by this change (BIAP defects)** | CAN RAT RGL RBW 1SN |

So **101 of 106** are genuine upstream/source facts; **5** were BIAP defects and are fixed.

## Ten+ blockers inspected at source level

| Ticker | Production result | Root cause (verified) | Action |
|---|---|---|---|
| **CAN** Canal+ | BLOCK, OFFICIAL_STALE FY2024 | FR ISIN ⇒ `locator_for` returned only the French AMF locator ("lists no ESEF"); FY2025 tagged ESEF zip `NI-000140865` (2026-03-17) sits on the FCA NSM and was never queried. | **Fixed** (F1) |
| **RAT** Rathbones | BLOCK, OFFICIAL_STALE FY2024 | FY2025 package is `…-2025-12-31.xbri` (`NI-000151833`); `UKNSMLocator` only kept links ending zip/xhtml/html. | **Fixed** (F2) |
| **RGL** Regional REIT | BLOCK `fundamental_core_figures` | iXBRL tags no `ProfitLoss` and no `Revenue` (only PBT, tax, owners' profit); P&L core test saw nothing. | **Fixed** (F3) |
| **RBW** Rainbow Rare Earths | BLOCK `fundamental_core_figures` | Same: only `ProfitLossBeforeTax` (-3,154k), tax 0, comprehensive income -3,154k. | **Fixed** (F3) |
| **1SN** First Tin | API_FAILURE | Catalog lists it (LSE adapter certified the row) but `/analyze` re-ran the generic digit-led-ticker guard without that certification and refused it. | **Fixed** (F4) |
| MNTL Technology Minerals | BLOCK, FY2024 | FY2025 NSM package (`NI-000142287`) embeds LEI `2138009GSW8ZDUU33943`, not the issuer's `2138001U1U2XY5UYA479`. | Correctly blocked — LEI gate **not** relaxed |
| MCG Mobico | BLOCK `fundamental_core_figures` | Period 2025-01-01→2026-03-31 (15 months); annual-duration facts (300–400 d) correctly not matched. | Legit fiscal transition |
| PTEC Playtech | BLOCK, FY2024 | FY2025 lodged as PDF + RNS only (`tag_esef` empty); last tagged zip is FY2024. | Legit upstream gap |
| BYG Big Yellow | BLOCK, FY2022 | Only one tagged zip ever (FY2022); FY2026 exists only as RNS "Final Results". Candidate for the reviewed-registry route (manual transcription of audited numbers), not auto-parsing. | Not changed (no fabrication) |
| AIC Achilles / EJFZ | BLOCK | Annual report lodged "Untagged" (2026-10-09 / 2026-03-27). | Legit (refused by design) |
| KAKU / ZOYO / VOX | BLOCK | GLEIF has 0 active matches for the ISIN/name; identity cannot be proven. | Legit |

## Fixes (UK-only, tests: `analysis/tests/test_global_uk_audit_fixes.py`, 13 tests)

* **F1** `NationalOAMESEFProvider.locators_for`: for `country == "GB"` the home-state OAM is tried first, then the FCA NSM. Error text is unchanged when only one locator applies. LEI re-check of the package entity is unchanged.
* **F2** `UKNSMLocator` accepts `.xbri` ESEF packages (already handled by the zip parser).
* **F3** `normalized_fields(..., derive_net_income=True)` (passed only for GB): net income = PBT − income tax, labelled `net_income_method = derived_profit_before_tax_minus_income_tax_same_period`, only when the filing tags **neither** a `ProfitLoss` total **nor** a revenue total, both lines exist for the year and no discontinued-operations result is tagged. Filings that already pass keep exactly their values (checked on the 7 PASS names with `net_income=None`: AIRE BRK CRST EMG GEN SFR SWC unchanged). RGL derived −16,352k = owners' profit; RBW −3,154k = comprehensive income.
* **F4** `service._supported_operating_equity`: honour the LSE adapter's `official_universe` + `lse_description` certification for GB, mirroring the catalog (`cached_universe`). Structural guards (`.PR`, currency, CFI) still apply.

## Before / after (isolated data dirs, `FUNDAMENTALS_CACHE_HOURS=0`, production untouched)

| Ticker | Before | After |
|---|---|---|
| CAN | BLOCK (OFFICIAL_STALE FY2024) | PASS, NSM `FCA-NSM:NI-000140865`, FY2025-12-31, revenue €6.949bn |
| RAT | BLOCK (FY2024) | PASS, official-oam-gb-fca-nsm FY2025-12-31 |
| RGL | BLOCK | PASS, net income −£16.352m (derived), assets 636.6m = liabilities 317.3m + equity 319.3m |
| RBW | BLOCK | PASS, net income −$3.154m (derived) |
| 1SN | API_FAILURE | PASS, NSM FY2025-06-30 |
| AZN, BYG, 7 net-income-None PASS names | PASS / BLOCK / PASS | unchanged |

All five calls are `NO_RECOMMENDATION`; no BUY is created or changed.
Projected GB: **PASS 421 → 426 (80.8 %)**, BLOCK 105 → 101, API failure 1 → 0. Projection from per-ticker re-runs, not a full re-audit; takes effect only after deploy + fundamentals cache refresh (not done here).
Tests: full suite `1170 passed` (clean env, repo venv).

## Notes

* **SUSPECT_VALUES 61 is an audit-tool false positive.** `_value_flags` flags every PASS whose reporting currency differs from the trading currency, but BIAP's P/E is already FX-converted: for all 71 such names `P/E ÷ (price ÷ EPS)` equals the FX rate (USD 1.317, EUR 1.167, HKD 10.27, ZAR 23.5). The tool (shared across markets) was not changed; recommended follow-up: flag only when that ratio is ≈ 1.
* Coverage gaps remaining are source facts: 50 + 18 names have no iXBRL for the newest year, 18 have no provable LEI. Closing them needs either the reviewed-registry route (manual, hash-pinned, audit-opinion checked) or a policy decision on investment-vehicle/AIM treatment — neither done here.
* The audit run also executed the tool's default SE/NO canary calls against the public API (read-only, unchanged). Analyze calls populate the production service's normal caches; no data or code in production was modified, deleted or deployed.
* Memory item still open: suspended-stock price freshness (GCG) is cross-market and untouched.
