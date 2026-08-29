# BIAP Module Data Reality Audit

Prepared on branch `chatgpt/module-data-audit-prep` so production `main` is untouched.

## Goal

Make every listed-company analysis module consume one normalized, provenance-aware company dataset built from verified public sources, and prevent demo/mock values from being presented as real analysis.

Target flow:

`Selected Company -> Company Resolver -> Shared Data Orchestrator -> CODAL + TSETMC/Tindex + Kiasha/Market + Market Memory -> Normalized Company Dataset -> Analysis Modules`

## What is already real in the current backend

### Shared company builder — REAL/PARTIAL

`analysis/company_builder.py` already acts as a partial shared data layer.

Verified inputs currently wired:

- CODAL metadata and scoped financial fundamentals
- CODAL audited filing evidence for audit opinion / related-party risk
- TSETMC live quote + extended market fields
- optional Tindex snapshot/performance/flow
- BIAP Market Memory as an explicitly stale/non-live fallback

Positive behavior already present:

- Missing market fields remain `None` rather than fabricated.
- CODAL-only company records can still be built when live market access is missing.
- Market Memory is explicitly marked non-live.
- `data_available` identifies source availability.

Gaps to fix before this can be the canonical dataset for every module:

- No single top-level provenance object per normalized field.
- Freshness is inconsistent across sources.
- There is no module contract declaring required/optional inputs.
- Different UI/backend modules may still bypass `company_builder.py` entirely.

Status: **PARTIAL shared data layer, good foundation.**

### Scenario / directional forecast — REAL/PARTIAL

`analysis/scenario_engine.py` is grounded and does not fabricate exact prices.

It currently consumes:

- CODAL revenue growth
- current/previous net margin
- Tindex 1m/3m/6m performance
- Tindex flow
- BIAP Market Memory history
- verified volatility

It explicitly reports missing data and returns `insufficient_verified_data` if no verified forecast inputs exist.

Important limitation:

- If only one Market Memory snapshot exists, there is not enough dated history for an actual trend.
- This is directional scenario analysis, not a statistical price forecast model.

Status: **REAL for directional scenarios when inputs exist; PARTIAL as a full forecast module.**

### Kiasha recommendation — REAL for verified path

Current project status documents a production path where the recommendation endpoint is using CODAL fundamentals, financial statement scope, audit opinion, related-party evidence and extended market data. This is already the strongest proven real-data route in BIAP and should become the reference pipeline for other modules.

Status: **REAL on verified supported-company path.**

## Initial module matrix

| Module | Current reality status | Intended canonical inputs | Main gap |
|---|---|---|---|
| Company/stock core dataset | PARTIAL/REAL | CODAL + TSETMC + Tindex + Market Memory | provenance schema + universal adoption |
| Kiasha recommendation | REAL | shared company dataset | expose/reuse more structured fields downstream |
| Scenario Analysis | REAL/PARTIAL | CODAL + Tindex + Market Memory | richer history + explicit source provenance |
| Forecast | PARTIAL | price/history + fundamentals | distinguish directional scenario from quantitative forecast |
| Risk | REAL/PARTIAL | audit + related-party + drawdown/range | verify every UI path consumes backend result |
| Fundamentals/KPI | REAL/PARTIAL | CODAL + market | ensure UI modules do not use separate demo values |
| Financial Model | UNKNOWN/PARTIAL | scoped CODAL statements | audit calculation path and eliminate CSV/demo fallback |
| Valuation/Pricing | UNKNOWN/PARTIAL | earnings/equity/cashflow + market cap/price | audit source and model assumptions |
| Anomaly Detection | UNKNOWN | dated real history | identify implementation and history source |
| SWOT | UNKNOWN/PARTIAL | evidence from real public/company data | prevent generic/fabricated statements |
| EDA | UNKNOWN/PARTIAL | same normalized dataset | inspect UI data source |
| Dashboard | UNKNOWN/PARTIAL | same normalized dataset | inspect UI data source |
| Reports | UNKNOWN/PARTIAL | same normalized dataset + provenance | inspect report generation path |
| Unit Economics | NOT VALID FOR MOST LISTED-COMPANY PUBLIC DATA | internal operating data | require internal data instead of fabricated proxy |
| CRM | INTERNAL-DATA REQUIRED | customer/internal CRM | never substitute stock-market data |
| Customer Journey | INTERNAL-DATA REQUIRED | customer/internal events | never substitute stock-market data |
| Campaign | INTERNAL-DATA REQUIRED | campaign/customer data | never substitute stock-market data |

`UNKNOWN` here means not yet traced end-to-end from source through calculation to rendered output. It does **not** mean broken.

## Required normalized dataset contract

Every listed-company module should receive one object with at least these groups:

```text
identity
  symbol / instrument code / company name / market

financials
  scoped CODAL statement metrics
  report scope
  report period
  filing id / tracing number

market
  current price / close / prior close
  market cap / shares / P-E / sector P-E
  volume / value / range / flow

history
  dated verified market observations
  source and freshness per series

riskEvidence
  audit opinion
  related-party flags
  source filing

provenance
  source per field or field-group
  source timestamp
  fetch timestamp
  freshness/live-vs-memory
  missing/unavailable reason
```

## Non-negotiable behavior

1. No silent demo fallback in listed-company analysis.
2. Missing verified input => `DATA_UNAVAILABLE` / `insufficient_verified_data`, not invented values.
3. Public-stock data must not be used to fake CRM, Customer Journey, Campaign or other private-company data.
4. A 200 HTTP response is not proof of a real module. The value must be traced into the final calculation/rendering path.
5. Changing selected company must change module input/output where company-specific real data exists.
6. Important metrics must preserve source, period and freshness.

## Next implementation pass

When coding resumes, audit in this order because it maximizes reuse:

1. Turn `company_builder.py` into the formal normalized dataset/orchestrator contract rather than a Kiasha-only helper.
2. Add a machine-readable provenance/freshness object.
3. Add module input contracts: `required`, `optional`, and `internal_only` fields.
4. Trace Financial Model, KPI, Dashboard, EDA, Report and SWOT first.
5. Trace Pricing/Valuation, Forecast and Anomaly next.
6. Gate CRM/Customer Journey/Campaign/Unit Economics behind internal-data availability.
7. Add end-to-end tests on at least three issuers, including فولاد, proving source -> normalized field -> calculation -> output.

## Acceptance test template

For each module and each test issuer record:

```text
module
selected_company
input_field
normalized_value
source
source_period
fetch_timestamp
calculation_used = true/false
rendered_output
status = REAL | PARTIAL | DEMO | BROKEN | INTERNAL_DATA_REQUIRED
```

A module may only be marked `REAL` after at least one important rendered/calculated output can be traced back to a verified source and a second company produces appropriately different input/output.
