# BIAP Mobile connection audit — 2026-08-30

Purpose: verify which user-facing flows are actually connected, which are local/demo, and which still need external/server integration before calling the Android build production-ready.

## Connected and doing real work

- Auth: signup/login/access token/refresh token against `https://biap.dadashi.no/api`; shared `authFetch` refresh path is used by the main authenticated FIN requests.
- Market: broad symbol universe plus verified quote attempts; missing prices remain blank rather than fabricated.
- Stock detail: symbol resolution, quote/history attempts, Kiasha recommendation, decision card, Demo trade, manual external-broker tracking, favorites.
- Kiasha: real recommendation/discovery pipeline, six-agent observed performance, short/long horizon ranking, server-owned Paper portfolio.
- Portfolio/Orders: explicit Demo-vs-Paper source split; Demo wallet is local, Paper is server-owned.
- Paper AI: server-side deterministic risk gate and Paper execution exist; live broker execution remains disabled.
- Data analysis modules: EDA/Dashboard/KPI/Anomaly/Report and performance-oriented modules can consume connected BIAP market/Kiasha data.
- Company dataset bridge: pasted CSV or JSON can now be parsed on-device and used by generic module summaries without inventing unavailable fields.

## Important limitations / not fully connected yet

1. Company data is currently **device-local AsyncStorage**, not authenticated server-owned data. It does not sync across devices/accounts and should not be described as a server connector.
2. The current company input accepts **pasted CSV/JSON**. It is not yet a real `.xlsx`/file-picker upload pipeline despite the UX mentioning CSV/Excel.
3. SQL, CRM/ERP and Custom API connectors are not live. They require a real external endpoint/credentials and must keep secrets server-side.
4. Business modules share a generic dataset summarizer. They are grounded in the imported dataset, but SWOT/CRM/Pricing/Financial Model/etc. are not yet dedicated backend analysis engines with domain-specific schemas.
5. `analysis/scenario_engine.py` exists on the server side, but there is no finished authenticated mobile/API bridge for the generic business Scenario module.
6. Real-money broker API is not connected. The current real-world workflow is broker-neutral manual tracking; raw card/broker secrets must never be stored in mobile.
7. Auto Invest is intentionally presented as SOON in the current public Kiasha UI even though guarded Paper automation exists server-side. Live trading remains off.
8. Favorites persist on-device and are visible on stock detail, but Market currently has no Favorites filter/list.
9. Stock-detail Kiasha retry still returns to the same empty state when upstream data remains unavailable; it needs an explicit retry-result message/timestamp so the button does not appear broken.
10. Kiasha Paper summary currently uses a fixed PAPER label even when `fetchPaperPortfolio()` is sourcing the local Demo wallet. UI should label Demo vs Paper from the actual source.
11. The standalone `تحلیل داده` screen is still primarily a market-data dashboard/export page; the broader analysis-module/data-source flow lives under Modules/Data Connections and should be linked more clearly.
12. `more.tsx` previously removed only accessToken/user on logout and could leave refresh credentials behind. Fixed by routing logout through `clearAuthSession()`.
13. Profile displays app version `1.0.0` as a hard-coded string instead of reading app metadata.

## APK gate

Before the next final APK: TypeScript must pass on latest main, then device-test login refresh/logout, Market/stock detail, favorites, Demo and Paper order/portfolio consistency, Kiasha short/long picks, missing-data retry UX, Data Connections, imported CSV/JSON dataset, all module Real/Demo states, and ensure no screen labels local/demo data as LIVE/PAPER incorrectly.
