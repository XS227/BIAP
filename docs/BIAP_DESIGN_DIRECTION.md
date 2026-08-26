# BIAP Mobile – Design Direction

## Product
BIAP is a Persian-first investment app for the Iranian stock market.
The visual direction is premium fintech: simple, trustworthy, fast and AI-assisted.

## Core user journey
1. Download/open app
2. Register or sign in
3. Receive 5 free AI analyses
4. Browse Iranian market and watchlist
5. Buy/sell stocks through the connected trading infrastructure
6. Use an AI investment agent such as **Kiasha (کیاشا)**
7. Agent provides analysis, risk guidance, suggested actions and—only where technically and legally enabled—automated investing

## Language and layout
- Primary UI language: Persian
- RTL layout throughout
- Persian numerals may be used for display, but data/API values should remain numeric internally
- Clear financial terminology and short labels

## Main navigation
- خانه
- بازار
- سفارش‌ها
- پرتفوی
- کیاشا
- بیشتر

## Key screens
### Welcome
- BIAP logo
- سرمایه‌گذاری هوشمند با BIAP
- دانلود اپ
- ثبت‌نام
- ورود

### Registration
- نام و نام خانوادگی
- ایمیل
- شماره موبایل
- رمز عبور
- Offer card: **۵ تحلیل رایگان**

### Dashboard
- پرتفوی من
- بازار امروز
- دیده‌بان من
- خرید
- فروش
- تحلیل
- Mini charts and Iranian market indicators

### AI Agent – Kiasha
- عامل هوشمند: کیاشا
- فعال‌سازی
- پیشنهاد خرید
- مدیریت ریسک
- گزارش عملکرد
- سرمایه‌گذاری خودکار (only when backend, brokerage permissions and compliance support it)

## Design system
- Primary blue: #125BFF
- Secondary purple: #7A20FF
- Background: #F7F8FC
- Surface: #FFFFFF
- Positive: #12B981
- Negative: #EF476F
- Text: #10152B
- Rounded cards: 18–24px
- Large touch targets and simple line icons
- Avoid dense desktop-trading UI on mobile

## Brand meaning
The BIAP wordmark should connect all four letters.
The outer b / p relationship suggests infinity, balance and continuity.
The central ai communicates AI between market data and investment decisions.

## Included files
- assets/brand/biap-logo.png
- assets/brand/biap-logo.svg
- assets/brand/biap-app-design-reference.jpg
- src/theme/biap.ts

## Suggested implementation order
1. Add theme and RTL foundation
2. Build Welcome + Registration
3. Add 5-free-analysis entitlement state
4. Rebuild dashboard around current live BIAP API
5. Add stock details + order flow
6. Add Kiasha agent screen
7. Connect actual broker/order execution only after backend permissions, security and compliance are ready

## Important
The reference image is a visual direction, not a source of hard-coded market values.
All portfolio, market, price, performance and order data must come from real backend/API sources.
