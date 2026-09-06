# Listed-company completion plan — 2026-09-06

Owner: ChatGPT session
Branch: `chatgpt/finish-listed-company-data-flow`
Tracking: #26

Scope:
1. Persist the public-market data needed by KPI, SQL / Data Query, and Financial Model for TSE / IFB companies so the mobile app can answer from stored verified data even when an upstream is temporarily unavailable.
2. Refresh market-derived fields daily and refresh the baseline company/public fundamentals coverage at least weekly. Tindex, TSETMC and CODAL provenance must stay explicit; unavailable values remain null.
3. Make the mobile listed-company path company-first: user chooses a listed company, then KPI / SQL / Financial Model load its stored public data directly. Upload/connect-company-data stays for private/internal fields only.
4. Fix the production signup/login email path that prevents a fresh mobile user from entering the app.
5. Do not enable live brokerage execution and do not fabricate missing values.

This file is a coordination marker so other agents do not create a competing implementation while this branch is active.
