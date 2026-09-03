# Kiasha Capital Mandate

Status: approved product/accounting strategy (2026-09-04)

## Goal

Kiasha Auto Invest must operate only on capital that the authenticated user explicitly delegates to Kiasha. The rest of the Paper account remains available for user-directed Paper trading. Manual/external-broker tracking is a separate ledger and must never contaminate Kiasha performance.

This is an accounting and risk boundary, not only a UI feature.

## Core invariants

1. **Explicit mandate only.** Kiasha may never size a BUY from the user's full Paper equity. Auto Invest may use only the active mandate's capital.
2. **Reserved capital is unavailable to manual Paper BUYs.** Once a mandate is active, its uninvested cash is locked for Kiasha until the mandate expires or is safely stopped.
3. **No cross-ledger P/L.** User-directed/manual trades cannot improve or reduce Kiasha Track Record. Kiasha Track Record includes only Kiasha-owned positions, cash, fills, realized P/L and mark-to-market P/L.
4. **No fabricated accounting.** Unknown prices remain unknown; an incomplete mark-to-market cannot be silently substituted with cost or zero.
5. **No overdraft.** Kiasha available cash may never become negative. A proposed order that would exceed mandate cash is rejected before execution.
6. **No hidden leverage.** The mandate is cash-only Paper capital. No margin, borrowing, synthetic leverage or reuse of unsettled/locked value.
7. **Risk policy still wins.** Capital allocation is an upper bound, never permission to bypass symbol concentration, daily notional, realized-loss, stale-price or market-session gates.
8. **User ownership.** The user can disable new Kiasha entries at any time. Disabling must not strand the ledger or pretend open positions are cash.
9. **Safe stop.** `STOP_REQUESTED` blocks new BUYs immediately. Existing Kiasha positions are either held until the configured exit policy/time horizon or liquidated through the same verified-price and risk-controlled Paper SELL path. Capital becomes withdrawable/available only after it is actually cash.
10. **Idempotent money movement.** Allocate, fill, sell, release and stop operations must be transactional/idempotent so retries cannot reserve/debit/release twice.

## Mandate lifecycle

`DRAFT -> ACTIVE -> STOP_REQUESTED | EXPIRING -> CLOSED`

- **DRAFT:** amount and horizon selected but no funds locked.
- **ACTIVE:** capital reserved; Kiasha may trade within policy.
- **STOP_REQUESTED:** no new BUYs; existing positions follow controlled exit rules.
- **EXPIRING:** horizon reached; no new BUYs; positions are being closed/settled according to policy.
- **CLOSED:** no Kiasha positions remain; all remaining mandate cash is released to available Paper cash.

## Supported horizons

Initial product choices:

- **1 week** (`1w`)
- **1 month** (`1m`)

The horizon is a mandate/risk horizon, not a promise that every position is held exactly that long. Kiasha may exit earlier when its verified signal/risk policy requires it. At horizon end it may not silently roll the mandate forward; renewal requires explicit user action.

## Paper-account accounting

Expose distinct balances instead of one ambiguous "main balance":

- `totalPaperEquity`
- `availablePaperCash`
- `kiashaAllocatedCapital`
- `kiashaCash`
- `kiashaInvestedValue`
- `kiashaPnL`
- `manualPaperInvestedValue` (only for true user-directed Paper orders)
- external/manual-broker tracked positions remain outside Paper cash accounting

Accounting identity (when all positions have verified marks):

`totalPaperEquity = availablePaperCash + kiashaCash + kiashaInvestedValue + manualPaperInvestedValue`

A mandate allocation is a transfer between internal Paper buckets, not a gain/loss and not a market order.

## Kiasha sizing

All Auto Invest sizing uses mandate equity/cash, never account-wide equity:

- `mandateEquity = kiashaCash + verified market value of Kiasha-owned positions`
- per-symbol cap is calculated from `mandateEquity`
- daily Auto Invest budget is calculated from `mandateEquity`
- a BUY must satisfy both Kiasha policy and `fillCost <= kiashaCash`

Manual Paper positions are excluded from those calculations.

## Fair Track Record

Kiasha performance is measured from the mandate ledger only.

Required snapshot fields:

- mandate id
- snapshot date/time
- allocated principal
- Kiasha cash
- verified Kiasha positions value
- total mandate equity
- cumulative realized P/L
- unrealized P/L when all required verified marks are available

User manual/external trades are never included in Kiasha return calculations.

When the necessary verified market price for an open Kiasha position is unavailable, the snapshot is marked incomplete/skipped according to the existing BIAP no-fabrication rule; it must not substitute an invented price.

## Manual Paper protection

Before a user-directed Paper BUY:

`manual spendable cash = availablePaperCash`

The order must be rejected if it would consume Kiasha-reserved cash. User-directed SELLs remain allowed for positions actually owned by the manual Paper ledger.

External broker trades recorded with "خریدم" remain tracking-only and do not debit either Paper bucket, because BIAP does not know the user's real broker cash balance.

## API direction

The backend should expose an authenticated mandate resource, for example:

- `GET /performance/ai/auto-invest/mandate`
- `PUT /performance/ai/auto-invest/mandate` — set amount + `1w|1m`, activate transactionally
- `POST /performance/ai/auto-invest/mandate/stop`

Status should include lifecycle state, start/end timestamps, allocated principal, available Kiasha cash, invested value (when verifiable), and whether withdrawals/releases are currently possible.

Existing `/performance/ai/auto-invest` settings can remain the runner/settings surface, but enabling the runner must require an ACTIVE mandate with positive delegated capital.

## Migration safety

Existing Paper accounts/positions predate ownership buckets. Do not guess whether historical positions were Kiasha or user-directed. Existing positions must be classified from authoritative audit/decision events where possible; otherwise mark ownership `legacy_unclassified` and exclude them from Kiasha Track Record until safely reconciled.

## Real-money future

If BIAP later connects an authorized broker, preserve the same mandate model. Broker authority must be scoped to the user-approved capital/risk mandate rather than unrestricted account balance. Real-money activation requires separate legal, broker, credential, settlement and regulatory controls; this Paper design does not enable live trading.