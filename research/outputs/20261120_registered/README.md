# Cohort P, one-month evaluation, registered script, exit 2026-11-20

**Primary result (as registered, nothing removed or corrected)**

| BUY | SELL | BUY-SELL spread | 95% CI | venues with positive spread |
|---|---|---|---|---|
| -2.281% | +6.611% | **-8.892 pp** | -49.694 to +12.855 | 11 of 12 |

Venue-equal means over 12 venues; 427 BUY and 487 SELL priced after ISIN dedup; bootstrap 10,000 draws, seed 20261020.

**This figure is dominated by a vendor data error.** GVMH (GB:LSE, SELL) moves between 0.006 and 0.6 GBp on little or no volume (at most 254 shares a day), which the
script reads as +9,900%. The runs of 19-25 November had 0.0% for the same holding.

## Comparison

| Run | Exit | Priced BUY/SELL | BUY % | SELL % | Spread pp | 95% CI | Venues + | Registered |
|---|---|---|---|---|---|---|---|---|
| This run | 20 Nov | 427/487 | -2.281 | 6.611 | -8.892 | -49.69 to 12.85 | 11/12 | yes |
| This run, without GVMH | 20 Nov | 427/486 | -2.281 | -13.059 | 10.778 | 7.95 to 13.51 | 12/12 | no, post hoc |
| This run, without GVMH, PDL, NUWE | 20 Nov | 427/484 | -2.281 | -13.098 | 10.817 | 8.06 to 13.52 | 12/12 | no, post hoc |
| Same data pull | 19 Nov | 427/487 | -0.405 | 8.759 | -9.164 | -50.00 to 12.68 | 11/12 | no |
| Same data pull, without GVMH, PDL, NUWE | 19 Nov | 427/484 | -0.405 | -10.970 | 10.565 | 7.65 to 13.46 | 12/12 | no, post hoc |
| Actions run 44705776623 | 19 Nov | 429/489 | -0.354 | -10.929 | 10.575 | 7.71 to 13.47 | 12/12 | no (earlier date) |
| Diagnostics, 25 Nov (`../20261119_extra`) | 19 Nov | see folder | -0.405 | -10.904 | 10.499 | 7.54 to 13.37 (seed 20261119) | 12/12 | no |

## Suspect vendor rows (`diagnostic_requery_20261127.txt`)

- GVMH (GB:LSE SELL): x100 unit flips, at most 254 shares a day. Not present in the earlier runs.
- PDL (GB:LSE SELL): 2.3 to 0.023 GBp on 2 Nov, no volume from 2 to 20 Nov; booked as -99.2%. Looks like the same x100 error. It was
  not among the restated rows, so it is also inside the earlier 19 November figures.
- NUWE (US:NASDAQ SELL): vendor lists a 1:9 reverse split on 27 Oct but does not adjust the entry close; booked as +520%. Also
  inside the earlier figures.

These three were found by a scan for day-to-day moves of 3x or more, not by checking every row against a second source.

## Coverage change

957 holdings have prices and 7 do not (961 and 3 in the Actions run). Yahoo no longer returns history for ERW.DE, LNAI, PFS0.F and
RAMP, and only two later days for FNGR; the script lists them as unpriced. Excluding rows flagged as delisted, the registered
sensitivity gives -9.087 pp (-50.93 to +13.25).

## Not verified

The OSF record (osf.io/6p8y7) and its protocol PDF were not opened; the repository tracking note says the primary endpoint is the
20 November spread and last records the registration as pending approval. Any rule there for data errors has not been applied.
