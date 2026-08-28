# BIAP Mobile V2 — Unified App Redesign Spec

Status: implementation target for the next Android/Expo build.
Source of truth: `XS227/BIAP/mobile/` on `main`.

## Goal

Turn the current consolidated BIAP mobile app into one polished unified application that exposes the important modules already available in `https://biap.dadashi.no/`, while keeping the current investment/Kiasha flows intact.

The redesign should follow the approved dark, modern BIAP mockup: navy/charcoal background, compact cards, blue/purple accents, clear Persian RTL typography, modern charts, and a premium financial-app feel.

Do **not** rebuild a second mobile app. Extend the existing `mobile/` app.

## Navigation

Keep a bottom navigation optimized for mobile. The primary investment flows must remain first-class:

- خانه
- بازار
- پرتفوی
- کیاشا
- بیشتر

`سفارش‌ها` can stay directly accessible from portfolio/market/Kiasha and may remain a bottom tab if the final layout still fits cleanly.

Under `بیشتر`, expose the BIAP business/data modules as grouped sections instead of hiding them:

### تحلیل داده
- EDA Explorer / تحلیل EDA
- SQL Query
- استخراج KPI
- تشخیص ناهنجاری
- تحلیل سری زمانی / پیش‌بینی آماری
- گزارش‌ساز / BI Dashboard

### KPI و داشبورد
- KPI dashboard
- KPI governance
- operational / sales / financial KPI cards
- export/report entry points where supported

### توسعه کسب‌وکار
- SWOT + رقبا
- Journey Map مشتری
- VOC + Friction Points
- CRM + Pipeline
- کمپین بازاریابی
- رفتار کاربر
- Business Plan
- قیمت‌گذاری هوشمند

### مدل مالی
- Scenario Analysis
- Financial Modeling
- Unit Economics
- گزارش MBR ماهانه

These modules may initially wrap or reproduce the existing web capabilities, but the mobile UI must feel native and consistent with the BIAP V2 design.

## Home screen

Create a real dashboard, not a menu-only page. It should include:

- BIAP brand/header and notification/settings entry
- market summary from real backend when available
- Kiasha recommendation summary
- portfolio summary (Paper portfolio now; real brokerage later)
- shortcuts to major module groups
- recent activity / last analysis / last order when real data exists

Never fabricate live market or user-account values.

## Kiasha / investment data

Investment screens must use only relevant market/investment sources: TSETMC, CODAL, Kiasha analysis, orders, and portfolio data. Business-development/EDA inputs must never silently affect stock recommendations unless a future explicit model integration is designed and documented.

Preserve:

- real symbol search
- Kiasha recommendation + four-agent breakdown
- CODAL facts
- observed Kiasha performance
- authenticated Paper orders and `/audit/orders`
- risk controls

## Portfolio V2

Until a real broker adapter/account connection exists, provide a clearly labeled **Paper Portfolio** derived from the authenticated user's actual Paper fills.

Portfolio must show, when derivable from real stored orders + real market price:

- symbol
- net quantity
- average Paper cost
- current price
- market value
- unrealized P/L amount and percent
- portfolio weight
- total Paper portfolio value
- total unrealized P/L

Do not present this as a real brokerage account. Add a clear `Paper / دمو` badge where appropriate.

When real brokerage connectivity is eventually implemented, this component should be replaceable by a broker-backed portfolio provider without redesigning the screen.

## Demo user / demo data policy

Demo data is allowed **only for an explicit Demo User / Demo Mode**.

Rules:

1. Real authenticated users: never inject fake financial, portfolio, market, order, KPI, CRM or company values when backend data is missing. Show an empty/unavailable state instead.
2. Demo user: curated demo datasets may populate modules so reviewers can experience the full product.
3. Every screen/card containing demo values must display a visible `DEMO / داده نمونه` badge.
4. Demo values must never be written into production user order/audit/portfolio records.
5. Demo mode must be deterministic and separated in code (for example `src/demo/`) so it cannot accidentally become a fallback for real users.
6. API-first behavior: use real API data when available even in demo UI unless the user explicitly entered Demo Mode.

## Visual language

- Dark navy base
- subtle elevated cards
- blue/purple primary accents
- green positive / red negative market signals
- compact modern charts
- large Persian numeric values
- RTL-first layout
- responsive for narrow Android devices
- consistent spacing/radius/theme tokens
- no white legacy BIAP web styling inside native screens

Prefer reusable module cards/components rather than duplicating styles per page.

## Architecture constraints

- `mobile/` remains the only source of truth for the app.
- Do not modify Kiasha/CODAL/auth backend logic just to satisfy UI design.
- Reuse current `mobile/src/lib/api.ts` and authenticated bearer-token handling.
- New APIs must be added only when a module genuinely needs data that is not exposed yet.
- Keep the rule: unavailable real data stays unavailable; no synthetic production numbers.
- Business/Data modules and investment modules should share the app shell/design system but stay logically separated.

## Validation before marking DONE

- `cd mobile && npm ci && npx tsc --noEmit`
- Expo on-device review on Android
- verify RTL and dark theme
- test real user mode: no demo leakage
- test explicit Demo User mode: all demo cards visibly labeled
- test Home, Market, Search, Portfolio, Orders, Kiasha, More
- test at least one module from Data, KPI, Business Development and Financial Model groups
- update `TASKS.md` with commits/build status

## Current baseline

Start from current `main`, which already contains:

- consolidated mobile app
- global search
- backend order history integration
- real JWT auth for order/audit endpoints
- Kiasha/CODAL integration

Do not revert those functional improvements while applying the V2 design.
