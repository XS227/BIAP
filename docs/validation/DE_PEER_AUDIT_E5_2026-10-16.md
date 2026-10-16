# DE peer benchmark audit E5: tender lines, revenue-less issuers, gate reconciliation (2026-10-16)

15 % threshold unchanged. All gate runs are dry runs on an isolated sqlite copy (`replaced=false`); no production repricing, merge, deploy, BUY change or deletion. Filings read transiently; only metadata stored.

## 1. "Z.VERK." tender-offer lines
| Line | ISIN | Instrument type | Evidence | Verdict |
|---|---|---|---|---|
| Ceconomy AG Z.VERK. | DE000A40ZVV0 | Shares tendered into the JD.com offer (not a separate issuer) | Eurex corporate-action page "Ceconomy AG Cash takeover" (updated 14 Nov 2025): DE000A40ZVV0 is the *tendered line*, replacing DE0007257503 as option underlying from 17 Nov 2025 | confirmed |
| Commerzbank AG Z.VERK. | DE000A41YE64 | Shares tendered into the UniCredit exchange offer | UniCredit offer document (5 May 2026): bidder will have tendered Commerzbank shares admitted to FSE trading under ISIN DE000A41YE64 | confirmed |
| Nagarro SE Z.VK. | DE000A41YFS0 | Shares tendered into the Persistent/Galaxy offer | Nagarro board/supervisory board reasoned statement names it the ISIN of tendered shares | confirmed |
| Delivery Hero SE VERK. | DE000A41YH12 | Probably tendered shares (Uber offer, acceptance period 27 Aug - 5 Nov 2026) | Only circumstantial (same naming pattern, price ~ stock); offer document sits behind a consent gate on delivering-value.com and I did not bypass it | **not confirmed** - treated as unverified |

**Effect on the gates: none.** These rows have no fundamentals, hence no P/E or P/B, so `freshness._non_member` already classes them `no_price_dependent_multiple`: they sit in neither the numerator nor the denominator (XETRA 17 and FRANKFURT 35 such non-members). Denominators stay 133 (XETRA) and 115 (FRANKFURT). I made no production-code change; regression test `analysis/tests/test_de_tender_lines_non_member.py` pins this behaviour. Earlier suggestion to remove them from the peer set is withdrawn: it would not move either gate.

## 2. Revenue-less issuers: policy implemented in `de_peer_doc_verify.py`
`decide()`: stored revenue > 0 must still be found in the filing. Stored revenue **None or exactly 0** is never read as zero and never fabricated; the row is tied to the filing by period phrase + net income + **EPS to the cent**, and `revenue_basis` is recorded as `not_verifiable`. Tests: 3 new (`test_de_peer_doc_verify_rounding.py`, 8 total).
Applied to the revenue-less rows with official documents in hand:
| Issuer | Result | Reason |
|---|---|---|
| Berliner Effektengesellschaft (BFV) | NOT_VERIFIED | group-report NI matches, but stored EPS 2.09 is not printed (filing EPS differs); stored row looks inconsistent |
| Deutsche Beteiligungs AG (DBAN) | NOT_VERIFIED | stored NI 26.4m is Konzern-Gesamtergebnis; Konzernergebnis is 24.698m; stored EPS 1.4 derives from the wrong line. Correct values: NI 24.698m (no revenue concept) |
| 029 Group SE (Z29) | NOT_VERIFIED | NI -2,334,332 matches, stored revenue 0.0 unverifiable, EPS -0.47 not printed |
| Webac Holding (RKB) | NOT_VERIFIED | NI matches, revenue 0.0 unverifiable, EPS 0.34 not printed |
No row could be promoted without loosening the rule, so none was.

## 3. Reconciliation (original denominators preserved)
| Gate | Members (denominator) | Excluded | Excluded % | Other checks | Result |
|---|---|---|---|---|---|
| XETRA before E5 | 133 | 17 | 12.8 | coverage 87.22, P/E 88.98, P/B 85.95 | DRY_RUN_OK |
| XETRA after E5 | 133 | 17 | 12.8 | unchanged | DRY_RUN_OK |
| FRANKFURT before E5 | 115 | 16 | 13.9 | P/B retention 82.14 (69/84) | REJECTED |
| FRANKFURT after E5 | 115 | 16 | 13.9 | P/B retention 82.14 (69/84) | REJECTED |
Change-by-change: tender lines 0 rows moved (already non-members); revenue-less policy 0 rows promoted; no row removed from or added to any denominator.

## 4. Frankfurt P/B retention: what remains (needs 72 of 84 retained, has 69)
P/B-bearing peers still undated (14) + 1 `filing_may_have_changed`:
verified-data blockers - DBAN (wrong line item), BFV (EPS mismatch), Scherzer PZS (stored revenue 10,000 EUR not in filing; NI and EPS match), Hyrican HYI (figures not in the HGB statement); no official 2025 group filing located - Netfonds NF4, ADM Hamburg OEL, DN Group D77, GBS 1GBS, Pittler PIT, SM Wirtschaftsberatung SMWN, ARI Motors ARI (statements promised on its IR site), Helios Solar HE8 (IPO 2026, no FY2025 report found); revenue-0.0 shells whose NI matches but EPS is not printed - Z29, RKB.
Three more verified rows (any of the above) lift FRANKFURT over 85 %. Documented policy options, **not applied**: (a) accept NI + EPS + period when a positive stored revenue is demonstrably wrong (would admit Scherzer); (b) treat a printed-NI-only match for revenue-0.0 shells (Z29, RKB) as sufficient. Both loosen the evidence rule and need owner sign-off.

## 5. Recommended ledger corrections (not applied; production data untouched)
DBAN NI 24.698m / EPS to recompute; PZS revenue to re-source; Vonovia revenue (filing 5,087.3m property management vs stored 5,061.3m); BFV EPS/NI basis.
