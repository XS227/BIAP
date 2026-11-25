# Paper revision note, 2026-11-07 (v2 only; protocol deviations to log for "From Abstention to Action")

Registered protocol: osf.io/6p8y7 (23 Oct 2026, paper test period 23 Oct – 19 Nov 2026). The paper-measured logic is **v1** and is not changed.

| # | change in v2 | why | effect | v1 |
|---|---|---|---|---|
| 1 | Agent 9 Zmijewski probability uses the probit link Φ(index) instead of the logistic link | Zmijewski (1984) is a probit model; the logistic link overstates P(distress) for index > 0 and understates it below | probabilities change; the Audit screen reads the same value; the distress gate (≥ 0.5) moves only for index near 0 (0.5 in both links at index 0) | unchanged (logistic) |
| 2 | BUY requires a valid positive P/E; otherwise ACCUMULATE with label «valuation unverified» | a BUY without any valuation figure is not defensible (owner decision 2026-11-07) | number of BUYs per market falls (see docs/reports STATUS file) | unchanged |

Both are decision-gate changes made after 23 Oct and are therefore **deviations**: date 2026-11-07, reason as above, scope v2 branch only, not deployed. Deploy date for v2: 20 Nov 2026 (after the test period).
