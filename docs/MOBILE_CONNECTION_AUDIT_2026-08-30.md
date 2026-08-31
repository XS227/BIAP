# BIAP Mobile connection audit — 2026-08-30 (resolved 2026-08-31)

Purpose: verify which user-facing flows are actually connected, which are local/demo, and which still need external/server integration before calling the Android build production-ready.

Status: every item below that could be closed with code (no external credentials, no licensed broker) was fixed the same night this doc was written or the following day. This file was not updated at the time, so it kept reporting fixed items as open — see the per-item notes for the commit that closed each one.

## Connected and doing real work

- Auth: signup/login/access token/refresh token against `https://biap.dadashi.no/api`; shared `authFetch` refresh path is used by the main authenticated FIN requests.
- Market: broad symbol universe plus verified quote attempts; missing prices remain blank rather than fabricated. Includes a Favorites filter (`market.tsx`, `category==='FAVORITES'`).
- Stock detail: symbol resolution, quote/history attempts, Kiasha recommendation, decision card, Demo trade, manual external-broker tracking, favorites, and an explicit retry-result message with timestamp when Kiasha data is unavailable.
- Kiasha: real recommendation/discovery pipeline, six-agent observed performance, short/long horizon ranking, server-owned Paper portfolio, and an opt-in Paper Auto Invest toggle (`kiasha-profile.tsx`) that reflects the real `runnerEnabled`/`paperExecutionEnabled` server flags — never fake-LIVE, never silently missing.
- Portfolio/Orders/Kiasha home: explicit Demo-vs-Paper source split driven by `PaperPortfolio.demo`, correct on `kiasha.tsx`, `portfolio.tsx`, and `orders.tsx`.
- Paper AI: server-side deterministic risk gate and Paper execution exist; live broker execution remains disabled.
- Data analysis modules: EDA/Dashboard/KPI/Anomaly/Report and performance-oriented modules can consume connected BIAP market/Kiasha data. `data.tsx` links prominently to Data Connections and Modules instead of acting as a dead-end dashboard.
- Company dataset bridge: server-owned, authenticated (`/business/dataset` GET/PUT/DELETE, `business_dataset_store.py`). Mobile syncs to the account, not just AsyncStorage. Accepts pasted CSV/JSON **and** a real `.xlsx` file picker (`expo-document-picker` + `/business/excel-import` + `excel_business_import.py`).
- Business Scenario module: `analysis/scenario_engine.py` is bridged through authenticated `POST /business/scenario`, consumed by `real-module-data.ts` and by the stock-detail `ScenarioPanel`.
- Profile shows the real app version via `Constants.expoConfig?.version`, not a hard-coded string.
- Logout routes through `clearAuthSession()`, clearing access + refresh token + user, not just accessToken/user.

## Still intentionally not live (by product/compliance decision, not a bug)

1. SQL, CRM/ERP and Custom API connectors: UI (`data-connect.tsx`) is built and honest about state (badge says "SETUP", not "LIVE"), but they stay inactive until a real external endpoint/credentials exist. Secrets would be server-side only.
2. Business modules (SWOT/CRM/Pricing/Financial Model/etc.) still share a generic dataset summarizer rather than dedicated domain-specific analysis engines. Grounded in the imported dataset, no fabricated fields — just not yet specialized. Scoped as separate future work.
3. Real-money broker API is not connected. Current real-world workflow stays broker-neutral manual tracking; raw card/broker secrets must never be stored in mobile. Per `BROKER_INTEGRATION.md`, live trading (`LIVE_TRADING_ENABLED`) stays fail-closed until a licensed broker supplies official integration material and production authorization — this is a deliberate compliance gate, not something to route around.

## APK build pipeline bug (found 2026-08-31, fixed)

The GitHub Actions APK build (`build-apk` job in `mobile-check.yml`) built the Android **debug** variant (`assembleDebug`). Debug builds under RN 0.86's default `debuggableVariants` don't embed the JS bundle — they expect a live Metro dev server reachable from the device. Installed standalone, the app showed the native splash screen (the big centered logo from `app.json`) and then hung forever, since there was no bundle to execute and no dev server to fetch one from. Fixed by building `assembleRelease` instead, which embeds the JS bundle and installs standalone (Expo's generated `build.gradle` signs release with the debug keystore by default, so no extra signing setup was needed).

## APK gate

Before the next final APK: TypeScript must pass on latest main, then device-test login refresh/logout, Market/stock detail, favorites, Demo and Paper order/portfolio consistency, Kiasha short/long picks including Auto Invest toggle, missing-data retry UX, Data Connections (CSV/JSON paste and real .xlsx import), all module Real/Demo states, and confirm the installed APK actually leaves the splash screen on a cold install (not just via Expo Go/dev client).
