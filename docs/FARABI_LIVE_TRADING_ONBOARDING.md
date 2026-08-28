# BIAP × Farabi — Live Trading Onboarding

Status: external broker access required before any live-money execution can be enabled.

## Goal

Connect BIAP/Kiasha to a licensed brokerage account so a user can:

1. see authenticated brokerage cash/buying power and real holdings,
2. fund the brokerage account through the broker/PSP flow,
3. create a reviewed order in BIAP,
4. explicitly approve the order,
5. submit it through the broker's official API,
6. receive broker order status/fill/cancel events back into BIAP.

BIAP must never collect raw bank-card PAN, CVV2, expiry, dynamic password/OTP, or route customer money into a BIAP-owned account.

## Provider requested first

Farabi Brokerage (کارگزاری فارابی).

Public support channel currently published by Farabi: 1561 (without area code).

Farabi publicly documents algorithmic/conditional trading and its Farabixo trading platform, but public documentation found so far does not provide the partner API credentials/specification needed for third-party BIAP execution. We therefore need a formal technical/business onboarding from Farabi.

## Exact access BIAP needs from Farabi

Ask Farabi for the following, preferably in sandbox/UAT first:

- Official third-party/partner trading API documentation.
- OAuth2 or equivalent customer authorization flow; no credential scraping.
- Sandbox/UAT environment and test account.
- Read buying power / cash balance.
- Read portfolio/positions.
- Read open orders and order history.
- Place BUY/SELL limit orders.
- Cancel/modify orders where permitted.
- Order-status and fill updates (webhook preferred; polling fallback).
- Instrument/symbol identifiers used by Farabi and mapping to TSETMC symbols.
- Rate limits, trading-session restrictions and idempotency requirements.
- Authentication/key-rotation requirements and IP allowlisting, if applicable.
- Official funding/deposit handoff: hosted URL, deep link, or broker-controlled PSP page.
- Withdrawal rules if BIAP may display or initiate withdrawal requests.
- Required customer consents, algorithmic-trading declarations and compliance approvals.
- Commercial/partnership terms for an external fintech application.

## Funding architecture

Correct flow:

`BIAP -> Farabi hosted funding/deposit flow -> PSP/bank -> customer's brokerage ledger`

After callback/return, BIAP refreshes buying power from the brokerage API.

BIAP does not receive or store card credentials and does not treat a PSP callback alone as proof of brokerage buying power; the broker balance API is authoritative.

## Order architecture

Recommended first production mode is human-approved live trading, not autonomous trading:

`Kiasha recommendation -> user enters quantity/limit -> BIAP risk checks -> confirmation screen -> user explicitly approves -> Farabi API -> broker order ID -> exchange status/fill -> BIAP audit log`

AUTO execution stays disabled until Farabi explicitly supports it and the required legal/compliance approvals, suitability/risk controls, limits and emergency kill switch are in place.

## Minimum safety controls before first real order

- Live mode disabled by default; separate from Demo/Paper.
- Broker account must be explicitly linked and verified.
- Display broker name and masked account identity before confirmation.
- Server-side buying-power validation immediately before submit.
- Server-side price-band/instrument/trading-session validation.
- Maximum order value and daily value limits.
- Duplicate/idempotency protection.
- Explicit second confirmation for live BUY/SELL.
- No live order from stale or unavailable market price without user-entered limit price.
- Immutable audit trail of intent, confirmation, broker request ID, broker response and fills.
- Cancel/replace reconciliation and periodic broker-order reconciliation.
- Emergency global LIVE_TRADING_ENABLED kill switch, default false.
- Broker secrets only on server-side secret storage; never embedded in Expo/mobile bundle or GitHub.

## Request text — Persian

موضوع: درخواست همکاری فنی و دسترسی API معاملات برخط برای پلتفرم BIAP / Kiasha

با سلام،

ما در حال توسعه پلتفرم BIAP و دستیار سرمایه‌گذاری هوشمند Kiasha هستیم. هدف ما اتصال کاربران به حساب معاملاتی خودشان نزد یک کارگزاری مجاز است؛ به‌گونه‌ای که تحلیل و پیشنهاد در BIAP انجام شود و ثبت سفارش واقعی فقط پس از تأیید صریح کاربر، از طریق API رسمی کارگزاری انجام شود.

برای بررسی همکاری با کارگزاری فارابی، لطفاً ما را به واحد فنی/فین‌تک/توسعه کسب‌وکار مرتبط با API معاملات و همکاری با پلتفرم‌های ثالث معرفی فرمایید. موارد موردنیاز ما شامل محیط Sandbox یا UAT، روش احراز هویت و اتصال حساب مشتری، دریافت قدرت خرید و پرتفوی، ثبت/لغو سفارش، دریافت وضعیت سفارش و معاملات انجام‌شده، و همچنین روش رسمی هدایت کاربر به فرآیند افزایش موجودی حساب کارگزاری است.

BIAP اطلاعات کارت بانکی کاربر را دریافت یا ذخیره نخواهد کرد و مسیر پرداخت باید کاملاً در بستر رسمی کارگزاری/PSP انجام شود. برای شروع نیز قصد داریم اجرای واقعی را فقط در حالت Human Approval فعال کنیم و معامله خودکار بدون تأیید کاربر را غیرفعال نگه داریم.

در صورت امکان لطفاً مستندات فنی API، شرایط دریافت دسترسی، الزامات حقوقی/امنیتی، محیط تست و مدل همکاری تجاری را ارسال فرمایید.

با احترام
تیم BIAP / Kiasha

## Short call script

«برای یک اپ فین‌تک به نام BIAP/Kiasha دنبال همکاری رسمی برای اتصال حساب کاربر و ارسال سفارش با API کارگزاری فارابی هستیم. لطفاً ما را به واحد فنی یا توسعه کسب‌وکار مربوط به API معاملات الگوریتمی/پلتفرم‌های ثالث وصل کنید. API عمومی یا اسکرپ کردن سامانه نمی‌خواهیم؛ دسترسی رسمی Sandbox و Partner API می‌خواهیم.»

## Implementation gate

Do not replace `PaperBroker` with a real broker implementation until Farabi supplies an official contract/specification and test credentials. Once supplied, implement a `FarabiBroker` adapter behind the existing broker interface, initially for approval-mode live orders only, with `LIVE_TRADING_ENABLED=false` by default.
