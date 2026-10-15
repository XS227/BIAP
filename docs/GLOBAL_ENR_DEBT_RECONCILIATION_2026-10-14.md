# ENR (Siemens Energy AG) debt reconciliation, FY to 2025-09-30

Status: **reconciled, calculation unchanged.** No code or data registry was modified for this note.

## Source and provenance

- Official ESEF package listed in `data/de_issuer_esef.json` (`SiemensEnergyAGKA-2025-09-30-v01-de-zip_Original file.zip`, host `assets.siemens-energy.com`, HTTP 200, no restriction bypassed).
- Package SHA-256: `7c7a97c9fd6079316d7d2fdd87c090628d2c478f84256586d209709b8ecd32ce`
- Report XHTML SHA-256: `67b20d81b6aa2059177a4a972fcd5b6aead161ece6cb5847158b4154d052db69`
- Language of the filing: German (Geschäftsbericht 2025).

## What the 3,966m is

BIAP's extension-concept value is the sum of two issuer-extension (`seag:`) balance-sheet concepts:

| Concept | 2025-09-30 (EUR m) | 2024-09-30 (EUR m) |
|---|---|---|
| `seag:ShortTermDebtAndCurrentMaturitiesOfLongTermDebt` | 1,528 | 479 |
| `seag:LongTermDebt` | 2,438 | 3,287 |
| Sum | **3,966** | 3,767 |

## Reconciliation to the notes (Konzernabschluss, Ziffer 13 "Finanzschulden")

| Component (EUR m, 2025-09-30) | Short-term | Long-term | Total |
|---|---|---|---|
| Liabilities to banks | 355 | 0 | 355 |
| **Lease liabilities** | 394 | 1,691 | **2,085** |
| Bonds and notes | 778 | 747 | 1,525 |
| Other financial debt | 0 | 0 | 0 |
| **Total** | 1,528 | 2,438 | **3,966** |

The movement table in the same note closes to 3,966 (opening 3,767, cash flows -599, FX -141, other +939). The issuer's own net-debt table in the management report ("Summe Finanzschulden") shows the same 3,966 and 3,767, so the extension concepts equal the issuer's reported total financial debt.

## Findings

1. **3,966m includes IFRS 16 lease liabilities of 2,085m.** Debt excluding leases is 1,881m (banks 355 + bonds 1,525 + other 0 = 1,880; 1m rounding).
2. This is consistent with the lease-inclusive `total_debt` basis already used for Deutsche Telekom in `de_verified_annual_reports.json`.
3. The `seag:` concepts are balance-sheet face lines, not a partial scope. They are safe to treat as total financial debt incl. leases once reviewed.
4. Other financial liabilities (current 782m, non-current 401m, `ifrs-full:OtherCurrent/NoncurrentFinancialLiabilities`) are separate and include derivatives; they are not in the 3,966m.
5. Cash and equivalents are 9,162m, so the issuer reports net liquidity of 5,196m, not net debt.

## D&A and impairment (unchanged conclusion)

- Cash-flow line "Abschreibungen und Wertminderungen" = 1,781m (combined; the only tagged line).
- Ziffer 10 discloses impairments of other intangibles and PP&E of 189m, "im Wesentlichen" related to the planned sale of the Indian wind business. The wording is qualified and goodwill/financial-asset impairments are reported elsewhere, so `1,781 - 189 = 1,592` is **not** an exact D&A.
- Segment note: "Amortisation, Abschreibung und Wertminderung" 1,781m (also combined).
- Issuer EBITDA 3,930m equals EBIT 2,149m + 1,781m exactly, i.e. the issuer's EBITDA adds back impairment. Its definition text was not located in the extracted report, so this is an arithmetic tie only.
- Therefore ENR is **not** added to `data/reviewed_da_lines.json`: the mechanism sums D&A concepts and never includes impairment lines, and no clean D&A line exists in the statements.

## Page references

The XHTML carries printed-page markers only as running headers. Ziffer 13 sits at printed pages 187-188 of the Konzernabschluss and the net-debt table at pages 195-196; exact page needs the PDF rendition and was not independently confirmed.

## Open decision (needs owner approval)

Supplying 3,966m to the engine needs a reviewed-debt path for issuers that are in the ESEF registry (the verified-reports file is scoped to issuers absent from it). EV/EBITDA would stay withheld because clean D&A is unavailable. Not implemented.
