# BIAP real-money brokerage integration

## Non-negotiable money flow

BIAP must **not** collect card PAN/CVV2/expiry/PIN and must **not** hold customer cash in a BIAP bank account.

For Iranian listed securities, the intended production flow is:

1. User connects an account at a licensed brokerage.
2. Funding is performed on a broker/approved PSP hosted page.
3. The payment beneficiary/credit is the customer's brokerage trading balance (or the broker's approved trading account flow), never BIAP.
4. BIAP reads broker buying power through an authorized broker API.
5. A BUY/SELL request is created in BIAP, passes risk/policy checks, and is shown to the user for explicit confirmation.
6. Only after confirmation is the order submitted through the broker adapter/API.
7. Broker order id, status, fills, fees, rejection reasons and timestamps are persisted to BIAP audit history.

This keeps payment custody and exchange access with regulated payment/broker infrastructure while BIAP acts as the analysis/order-intent experience.

## Required broker contract/API capabilities

Before enabling any real order button, the selected brokerage must provide and authorize all required capabilities:

- customer identity/account binding (prefer OAuth/short-lived authorization; never customer broker password in BIAP),
- trading balance / buying-power read,
- portfolio and open-order read,
- symbol/instrument mapping,
- order preview or validation where available,
- submit BUY/SELL limit order,
- cancel/replace order,
- order/fill status,
- hosted deposit/top-up URL or broker-approved PSP flow,
- withdrawal stays in the brokerage flow,
- documented rate limits, sandbox/test account and production credentials.

## Security controls

- Never store card numbers, CVV2, expiry, second password or OTP.
- Never put broker secrets in Expo/mobile code. Secrets live only on the backend.
- Use short-lived broker tokens where available and encrypt refresh credentials at rest.
- Default real trading to explicit human approval. AUTO remains disabled until separate legal/compliance approval.
- Every submit must use an idempotency key and be safe to retry.
- Re-check buying power, market status, price bands, quantity and symbol immediately before broker submission.
- Persist an immutable audit record of user confirmation and broker response.
- Demo/Paper wallets must never share balances, holdings or order ids with real brokerage accounts.

## Product UX

### Deposit

`کارت بانکی → درگاه امن کارگزاری/PSP → قدرت خرید حساب کارگزاری`

BIAP opens the broker-hosted funding flow. The user returns to BIAP after success and BIAP refreshes buying power from the broker API.

### Buy

`تحلیل BIAP → انتخاب تعداد/قیمت → پیش‌نمایش کارمزد و قدرت خرید → تأیید کاربر → Broker API → بورس`

### Sell

BIAP checks the broker portfolio/free quantity, shows an order preview, requires user confirmation and then submits through the broker API.

## Rollout plan

### Phase 1 — safe real-money pilot

- Connect one licensed broker.
- Broker-hosted funding/deposit only.
- Read balance/portfolio.
- Human-confirmed limit orders only.
- No AUTO trading.
- Small internal pilot accounts first.

### Phase 2

- cancel/replace,
- richer order lifecycle,
- multi-broker adapter support,
- stronger risk profiles and user limits.

### Phase 3

Only after broker + legal/compliance approval: evaluate conditional/algorithmic execution. AUTO remains disabled by default.

## Current BIAP state

`analysis/broker.py` already exposes a broker adapter boundary and only `PaperBroker` is implemented. `analysis/execution.py` deliberately blocks AUTO/live execution. This is correct and must remain locked until a real brokerage contract, production API docs and credentials are available.
