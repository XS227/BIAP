# BIAP × Farabi online-trading handoff — 2026-09-08

## Implemented now

BIAP Mobile can hand a real trade off to Farabi's official mobile online-trading surface, Farabixo Next:

- Official mobile trading URL used by the app: `https://m.farabixo.irfarabi.com`
- The BIAP recommendation card shows the selected symbol, quantity, reference price and approximate notional before handoff.
- The user chooses BUY or SELL in BIAP, then Farabixo Next opens for broker authentication and final order submission.
- Brokerage username/password, OTP and other authentication secrets remain inside Farabi; BIAP does not collect or persist them.
- After the user completes the trade in Farabi, they can return to BIAP and record the completed BUY/SELL so Kiasha portfolio/order tracking remains current.

This is an operational broker handoff, not a claim that BIAP has an undocumented private Farabi order API.

## Direct API status

Farabi publicly provides online, conditional and algorithmic trading products, but BIAP still does not have an official third-party/partner API contract, sandbox credentials, endpoint specification or customer authorization flow from Farabi.

Therefore:

- `LIVE_TRADING_ENABLED=false` remains the default for BIAP's server-side broker adapter.
- BIAP must not scrape Farabixo sessions or store Farabi credentials.
- Direct in-app order submission can replace the handoff only after Farabi supplies official partner/API documentation and test credentials.

See `docs/FARABI_LIVE_TRADING_ONBOARDING.md` and `analysis/broker_gateway.py` for the direct API integration gate.
