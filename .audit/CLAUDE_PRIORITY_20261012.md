# BIAP Global priority completion — 2026-10-12
Work on feat/biap-global. Prioritize US, GB, FR, IT, SE, NO. Germany conditional on verification. Do not expand other countries until paper readiness.
1. Audit raw official filings and normalized periods, currencies, units, EBIT/EBITDA/interest expense. Specifically reconcile Agent 9 ICR vs Agent 10 EBITDA/interest and cross-agent risk discrepancies (Volvo Cars), no synthetic official ratings.
2. Tesla TSLA: distinguish OFFICIAL_CURRENT vs last available annual filing (284-day age), and missing ICR limitations; do not claim stale data is fresh. Verify peer P/E and benchmark cohort.
3. Separate discovered, lightweight screened, deep-analyzed, evidence-PASS and qualified-buy coverage. 2997/3017 screened is NOT 75/3017 deeply analyzed.
4. Handle GOOG/GOOGL issuer duplicates correctly in company rankings and portfolio concentration, preserving separate securities where appropriate.
5. Check Agent 8 disagreement review, Agent 9 incomplete evidence and Agent 10 insufficient-data gates; do not weaken safety gates to force BUY.
6. Explain why portfolio rejects qualified candidates using traceable per-constraint reasons; do not force allocations.
7. Test official-source provenance, freshness and calculations with representative tickers across six countries, Germany separately, including TSLA, VOLCAR.B, ENI and financial entities. Validate live API and Android parity.
8. Add regression tests, run them, commit and push verified changes with a reproducible audit report including PASS/WARN/BLOCK per market, data timestamps and limitations. Green CI alone is not proof of correctness. Do not claim APK is validated without real installation tests.
Avoid conflicting with running work; inspect current branch/status first. Execute improvements autonomously and leave explicit next steps if blocked.
