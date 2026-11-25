# Risk Agent: CRITICAL / HIGH cases in the staging sample (2026-11-25)

Staging sample, 96 stocks, Risk Agent v2 inputs (statement-date FX, GDP deflator 1968=100, unit-scale check, interest coverage). Raw statement values are in the reporting currency, full units. Each value below is what BIAP stored; **not yet checked against the filings**. All Ohlson/Zmijewski/Altman inputs are ratios of these values.

Formulas: Altman Z''=6.56 WC/TA+3.26 RE/TA+6.72 EBIT/TA+1.05 E/TL; Zmijewski probit(-4.3-4.5 NI/TA+5.7 TL/TA-0.004 CA/CL); Ohlson per Ohlson (1980) with FUTL=operating cash flow/TL (proxy); interest coverage=EBIT/interest expense.

## CRITICAL: Wetteri Oyj (WETTERI, FI / NASDAQ_HELSINKI)

Status OK; reasons: Altman Z''=-0.64 (distress zone); Ohlson P(bankruptcy)=0.635 (O=0.55); Zmijewski P(distress)=0.531 (distress-likely); Interest coverage EBIT/interest=-0.48x (severe); annualised volatility 52%, max drawdown 56% (price-risk flag; capped at elevated)

Statement period end 2025-12-31, currency EUR, scope None; unit scale VERIFIED (ESEF xBRL-JSON (OIM): canonical absolute values, iXBRL scale already applied); FX to USD 1.175000 on 2025-12-31.

Stored statement values:

| field | value |
|---|---|
| revenue | 434,057,000.00 |
| revenue_prev | 447,293,000.00 |
| net_margin_prev_pct | -1.60 |
| operating_income | -4,538,000.00 |
| net_income | 4,267,000.00 |
| total_assets | 173,442,000.00 |
| total_liabilities | 136,692,000.00 |
| total_equity | 36,750,000.00 |
| retained_earnings | -10,756,000.00 |
| current_assets | 82,103,000.00 |
| current_liabilities | 96,459,000.00 |
| operating_cash_flow | 14,875,000.00 |
| interest_expense | 9,486,000.00 |
| total_debt | 1,740,000.00 |

Source: esef-xbrl-cached-v2 id=24764 https://filings.xbrl.org/743700TDB62DGAFROB24/2025-12-31/ESEF/FI/0/743700TDB62DGAFROB24-2025-12-31-1-fi/reports/ixbrlviewer.html

| model | value | severity | inputs |
|---|---|---|---|
| Altman Z'' | -0.6387 (DISTRESS) | 2 | working_capital_to_assets=-0.0828, retained_earnings_to_assets=-0.0620, ebit_to_assets=-0.0262, equity_to_liabilities=0.2689 |
| Ohlson O-score | 0.6353 (high) | 2 | o_score=0.5549, size=5.6664, total_assets_usd_thousands=203794.3500, fx_rate_to_usd=1.1750, fx_rate_date=2025-12-31, gdp_deflator_1968_100=705.1676, deflator_year=2025, tlta=0.7881, wcta=-0.0828, clca=1.1749, oeneg=0.0000, nita=0.0246, futl_ocf_proxy=0.1088, intwo=0.0000, chin=1.0000 |
| Zmijewski | 0.5311 (distress-likely) | 2 | index=0.0781, net_income_to_assets=0.0246, liabilities_to_assets=0.7881, current_ratio=0.8512, link=probit |
| Beneish M-score | not available | - | missing: receivables, gross_profit, ppe, depreciation, sga, receivables_prev, gross_profit_prev, ppe_prev, depreciation_prev, sga_prev, total_assets_prev, total_debt_prev |
| Interest coverage | -0.4784 (severe) | 2 | ebit=-4538000.0000, interest_expense=9486000.0000 |
| Price volatility | 51.6022 (high) | 1 | volatility_annualized_pct=51.6022, max_drawdown_pct=56.4736 |

## CRITICAL: TESMEC SPA (TES, IT / EURONEXT_MILAN)

Status OK; reasons: Altman Z''=1.25 (grey zone); Ohlson P(bankruptcy)=0.518 (O=0.07); Zmijewski P(distress)=0.628 (distress-likely); Interest coverage EBIT/interest=0.84x (severe); annualised volatility 70%, max drawdown 40% (price-risk flag; capped at elevated)

Statement period end 2025-12-31, currency EUR, scope None; unit scale VERIFIED (OAM filings read as ESEF xBRL-JSON (esef.py): canonical absolute values); FX to USD 1.175000 on 2025-12-31.

Stored statement values:

| field | value |
|---|---|
| revenue | 257,606,000.00 |
| revenue_prev | 239,546,000.00 |
| net_margin_prev_pct | -2.01 |
| operating_income | 19,519,000.00 |
| net_income | 2,127,000.00 |
| total_assets | 402,375,000.00 |
| total_liabilities | 328,645,000.00 |
| total_equity | 73,730,000.00 |
| retained_earnings | 1,691,000.00 |
| current_assets | 264,200,000.00 |
| current_liabilities | 222,973,000.00 |
| operating_cash_flow | 48,426,000.00 |
| interest_expense | 23,247,000.00 |
| total_debt | 7,757,000.00 |

Source: official-oam-it-emarket-storage id=EMARKET-STORAGE:180874 https://www.emarketstorage.it/it/documenti?categoria=100&azienda=5893

| model | value | severity | inputs |
|---|---|---|---|
| Altman Z'' | 1.2474 (GREY) | 1 | working_capital_to_assets=0.1025, retained_earnings_to_assets=0.0042, ebit_to_assets=0.0485, equity_to_liabilities=0.2243 |
| Ohlson O-score | 0.5176 (high) | 2 | o_score=0.0705, size=6.5080, total_assets_usd_thousands=472790.6250, fx_rate_to_usd=1.1750, fx_rate_date=2025-12-31, gdp_deflator_1968_100=705.1676, deflator_year=2025, tlta=0.8168, wcta=0.1025, clca=0.8440, oeneg=0.0000, nita=0.0053, futl_ocf_proxy=0.1474, intwo=0.0000, chin=1.0000 |
| Zmijewski | 0.6282 (distress-likely) | 2 | index=0.3270, net_income_to_assets=0.0053, liabilities_to_assets=0.8168, current_ratio=1.1849, link=probit |
| Beneish M-score | not available | - | missing: receivables, gross_profit, ppe, depreciation, sga, receivables_prev, gross_profit_prev, ppe_prev, depreciation_prev, sga_prev, total_assets_prev, total_debt_prev |
| Interest coverage | 0.8396 (severe) | 2 | ebit=19519000.0000, interest_expense=23247000.0000 |
| Price volatility | 69.8947 (high) | 1 | volatility_annualized_pct=69.8947, max_drawdown_pct=40.0494 |

## CRITICAL: GENERAL DE ALQUILER DE MAQUINARIA, S.A (GAM, ES / BME_MADRID)

Status OK; reasons: Altman Z''=0.01 (distress zone); Ohlson P(bankruptcy)=0.591 (O=0.37); Zmijewski P(distress)=0.585 (distress-likely); Interest coverage EBIT/interest=1.40x (elevated)

Statement period end 2025-12-31, currency EUR, scope None; unit scale VERIFIED (ESEF xBRL-JSON (OIM): canonical absolute values, iXBRL scale already applied); FX to USD 1.175000 on 2025-12-31.

Stored statement values:

| field | value |
|---|---|
| revenue | 316,113,000.00 |
| revenue_prev | 304,038,000.00 |
| net_margin_prev_pct | 1.43 |
| operating_income | 28,477,000.00 |
| net_income | 6,544,000.00 |
| total_assets | 562,735,000.00 |
| total_liabilities | 451,250,000.00 |
| total_equity | 111,485,000.00 |
| retained_earnings | -42,411,000.00 |
| current_assets | 151,868,000.00 |
| current_liabilities | 181,713,000.00 |
| operating_cash_flow | 97,629,000.00 |
| interest_expense | 20,372,000.00 |
| total_debt | None |

Source: esef-xbrl-cached-v2 id=26388 https://filings.xbrl.org/95980020140005731713/2025-12-31/ESEF/ES/0/95980020140005731713-2025-12-31-1-es/reports/ixbrlviewer.html

| model | value | severity | inputs |
|---|---|---|---|
| Altman Z'' | 0.0059 (DISTRESS) | 2 | working_capital_to_assets=-0.0530, retained_earnings_to_assets=-0.0754, ebit_to_assets=0.0506, equity_to_liabilities=0.2471 |
| Ohlson O-score | 0.5911 (high) | 2 | o_score=0.3685, size=6.8434, total_assets_usd_thousands=661213.6250, fx_rate_to_usd=1.1750, fx_rate_date=2025-12-31, gdp_deflator_1968_100=705.1676, deflator_year=2025, tlta=0.8019, wcta=-0.0530, clca=1.1965, oeneg=0.0000, nita=0.0116, futl_ocf_proxy=0.2164, intwo=0.0000, chin=0.2006 |
| Zmijewski | 0.5851 (distress-likely) | 2 | index=0.2151, net_income_to_assets=0.0116, liabilities_to_assets=0.8019, current_ratio=0.8358, link=probit |
| Beneish M-score | not available | - | missing: receivables, gross_profit, ppe, depreciation, sga, total_debt, receivables_prev, gross_profit_prev, ppe_prev, depreciation_prev, sga_prev, total_assets_prev, total_debt_prev |
| Interest coverage | 1.3978 (elevated) | 1 | ebit=28477000.0000, interest_expense=20372000.0000 |
| Price volatility | 28.6514 (normal) | 0 | volatility_annualized_pct=28.6514, max_drawdown_pct=20.1183 |

## CRITICAL: PROSEGUR CASH, S.A. (CASH, ES / BME_MADRID)

Status OK; reasons: Ohlson P(bankruptcy)=0.667 (O=0.70); Zmijewski P(distress)=0.784 (distress-likely)

Statement period end 2025-12-31, currency EUR, scope None; unit scale VERIFIED (OAM filings read as ESEF xBRL-JSON (esef.py): canonical absolute values); FX to USD 1.175000 on 2025-12-31.

Stored statement values:

| field | value |
|---|---|
| revenue | 1,987,329,000.00 |
| revenue_prev | 2,089,879,000.00 |
| net_margin_prev_pct | 4.36 |
| operating_income | 216,236,000.00 |
| net_income | 94,051,000.00 |
| total_assets | 2,746,061,000.00 |
| total_liabilities | 2,525,957,000.00 |
| total_equity | 220,104,000.00 |
| retained_earnings | None |
| current_assets | 1,491,237,000.00 |
| current_liabilities | 1,605,486,000.00 |
| operating_cash_flow | 209,716,000.00 |
| interest_expense | 61,292,000.00 |
| total_debt | None |

Source: official-oam-es-cnmv-ifa id=CNMV-IFA:20918:consolidated https://www.cnmv.es/portal/Consultas/IFA/ListadoIFA?id=0&nif=A87498564

| model | value | severity | inputs |
|---|---|---|---|
| Altman Z'' | not available | - | missing: retained_earnings |
| Ohlson O-score | 0.6672 (high) | 2 | o_score=0.6957, size=8.4285, total_assets_usd_thousands=3226621.6750, fx_rate_to_usd=1.1750, fx_rate_date=2025-12-31, gdp_deflator_1968_100=705.1676, deflator_year=2025, tlta=0.9198, wcta=-0.0416, clca=1.0766, oeneg=0.0000, nita=0.0342, futl_ocf_proxy=0.0830, intwo=0.0000, chin=0.0162 |
| Zmijewski | 0.7839 (distress-likely) | 2 | index=0.7853, net_income_to_assets=0.0342, liabilities_to_assets=0.9198, current_ratio=0.9288, link=probit |
| Beneish M-score | not available | - | missing: receivables, ppe, depreciation, sga, total_debt, receivables_prev, gross_profit_prev, ppe_prev, depreciation_prev, sga_prev, total_assets_prev, total_debt_prev |
| Interest coverage | 3.5280 (adequate) | 0 | ebit=216236000.0000, interest_expense=61292000.0000 |
| Price volatility | 20.3010 (normal) | 0 | volatility_annualized_pct=20.3010, max_drawdown_pct=13.5261 |

## HIGH: ENDÚR ASA (ENDUR, NO / EURONEXT_OSLO)

Status OK; reasons: Altman Z''=1.08 (distress zone); Ohlson P(bankruptcy)=0.264 (O=-1.03)

Statement period end 2025-12-31, currency NOK, scope None; unit scale VERIFIED (OAM filings read as ESEF xBRL-JSON (esef.py): canonical absolute values); FX to USD 0.099215 on 2025-12-31.

Stored statement values:

| field | value |
|---|---|
| revenue | 6,397,800,000.00 |
| revenue_prev | 2,766,900,000.00 |
| net_margin_prev_pct | 1.57 |
| operating_income | 322,000,000.00 |
| net_income | 134,400,000.00 |
| total_assets | 6,313,100,000.00 |
| total_liabilities | 3,965,500,000.00 |
| total_equity | 2,347,600,000.00 |
| retained_earnings | 141,800,000.00 |
| current_assets | 2,602,800,000.00 |
| current_liabilities | 2,566,500,000.00 |
| operating_cash_flow | 1,038,800,000.00 |
| interest_expense | 175,000,000.00 |
| total_debt | 914,600,000.00 |

Source: official-oam-no-oslo-newsweb id=NEWSWEB:671230:323853 https://newsweb.oslobors.no/message/671230

| model | value | severity | inputs |
|---|---|---|---|
| Altman Z'' | 1.0753 (DISTRESS) | 2 | working_capital_to_assets=0.0057, retained_earnings_to_assets=0.0225, ebit_to_assets=0.0510, equity_to_liabilities=0.5920 |
| Ohlson O-score | 0.2640 (elevated) | 1 | o_score=-1.0252, size=6.7892, total_assets_usd_thousands=626352.4867, fx_rate_to_usd=0.0992, fx_rate_date=2025-12-31, gdp_deflator_1968_100=705.1676, deflator_year=2025, tlta=0.6281, wcta=0.0057, clca=0.9861, oeneg=0.0000, nita=0.0213, futl_ocf_proxy=0.2620, intwo=0.0000, chin=0.5110 |
| Zmijewski | 0.2063 (watch band (20-50%)) | 0 | index=-0.8195, net_income_to_assets=0.0213, liabilities_to_assets=0.6281, current_ratio=1.0141, link=probit |
| Beneish M-score | not available | - | missing: receivables, gross_profit, ppe, depreciation, sga, receivables_prev, gross_profit_prev, ppe_prev, depreciation_prev, sga_prev, total_assets_prev, total_debt_prev |
| Interest coverage | 1.8400 (adequate) | 0 | ebit=322000000.0000, interest_expense=175000000.0000 |
| Price volatility | 26.4848 (normal) | 0 | volatility_annualized_pct=26.4848, max_drawdown_pct=19.5200 |

## HIGH: SENTIA ASA (SNTIA, NO / EURONEXT_OSLO)

Status OK; reasons: Altman Z''=1.55 (grey zone); Ohlson P(bankruptcy)=0.459 (O=-0.17); Zmijewski P(distress)=0.357 (watch band (20-50%))

Statement period end 2025-12-31, currency NOK, scope None; unit scale VERIFIED (OAM filings read as ESEF xBRL-JSON (esef.py): canonical absolute values); FX to USD 0.099215 on 2025-12-31.

Stored statement values:

| field | value |
|---|---|
| revenue | 11,772,000,000.00 |
| revenue_prev | 10,531,000,000.00 |
| net_margin_prev_pct | 4.60 |
| operating_income | 576,000,000.00 |
| net_income | 571,000,000.00 |
| total_assets | 6,949,000,000.00 |
| total_liabilities | 5,253,000,000.00 |
| total_equity | 1,696,000,000.00 |
| retained_earnings | 618,000,000.00 |
| current_assets | 5,522,000,000.00 |
| current_liabilities | 5,132,000,000.00 |
| operating_cash_flow | 1,015,000,000.00 |
| interest_expense | 11,000,000.00 |
| total_debt | None |

Source: official-oam-no-oslo-newsweb id=NEWSWEB:669537:322388 https://newsweb.oslobors.no/message/669537

| model | value | severity | inputs |
|---|---|---|---|
| Altman Z'' | 1.5541 (GREY) | 1 | working_capital_to_assets=0.0561, retained_earnings_to_assets=0.0889, ebit_to_assets=0.0829, equity_to_liabilities=0.3229 |
| Ohlson O-score | 0.4588 (elevated) | 1 | o_score=-0.1652, size=6.8852, total_assets_usd_thousands=689443.1310, fx_rate_to_usd=0.0992, fx_rate_date=2025-12-31, gdp_deflator_1968_100=705.1676, deflator_year=2025, tlta=0.7559, wcta=0.0561, clca=0.9294, oeneg=0.0000, nita=0.0822, futl_ocf_proxy=0.1932, intwo=0.0000, chin=0.0825 |
| Zmijewski | 0.3575 (watch band (20-50%)) | 1 | index=-0.3652, net_income_to_assets=0.0822, liabilities_to_assets=0.7559, current_ratio=1.0760, link=probit |
| Beneish M-score | not available | - | missing: receivables, gross_profit, ppe, depreciation, sga, total_debt, receivables_prev, gross_profit_prev, ppe_prev, depreciation_prev, sga_prev, total_assets_prev, total_debt_prev |
| Interest coverage | 52.3636 (adequate) | 0 | ebit=576000000.0000, interest_expense=11000000.0000 |
| Price volatility | 22.2392 (normal) | 0 | volatility_annualized_pct=22.2392, max_drawdown_pct=9.1533 |

## HIGH: OCI N.V. (OCI, NL / EURONEXT_AMSTERDAM)

Status OK; reasons: Altman Z''=2.10 (grey zone); Interest coverage EBIT/interest=-0.83x (severe)

Statement period end 2025-12-31, currency USD, scope None; unit scale VERIFIED (OAM filings read as ESEF xBRL-JSON (esef.py): canonical absolute values); FX to USD 1.000000 on 2025-12-31.

Stored statement values:

| field | value |
|---|---|
| revenue | 1,086,000,000.00 |
| revenue_prev | 975,100,000.00 |
| net_margin_prev_pct | 532.86 |
| operating_income | -112,700,000.00 |
| net_income | 183,800,000.00 |
| total_assets | 1,839,400,000.00 |
| total_liabilities | 764,600,000.00 |
| total_equity | 1,074,800,000.00 |
| retained_earnings | 128,300,000.00 |
| current_assets | 896,400,000.00 |
| current_liabilities | 670,700,000.00 |
| operating_cash_flow | -82,200,000.00 |
| interest_expense | 135,900,000.00 |
| total_debt | None |

Source: official-oam-nl-afm-register id=AFM:A2510-03652 https://www.afm.nl/en/sector/registers/meldingenregisters/financiele-verslaggeving/details?id=A2510-03652

| model | value | severity | inputs |
|---|---|---|---|
| Altman Z'' | 2.0966 (GREY) | 1 | working_capital_to_assets=0.1227, retained_earnings_to_assets=0.0698, ebit_to_assets=-0.0613, equity_to_liabilities=1.4057 |
| Ohlson O-score | 0.1560 (low) | 0 | o_score=-1.6886, size=7.8665, total_assets_usd_thousands=1839400.0000, fx_rate_to_usd=1.0000, fx_rate_date=2025-12-31, gdp_deflator_1968_100=705.1676, deflator_year=2025, tlta=0.4157, wcta=0.1227, clca=0.7482, oeneg=0.0000, nita=0.0999, futl_ocf_proxy=-0.1075, intwo=0.0000, chin=-0.9317 |
| Zmijewski | 0.0085 (distress-unlikely) | 0 | index=-2.3856, net_income_to_assets=0.0999, liabilities_to_assets=0.4157, current_ratio=1.3365, link=probit |
| Beneish M-score | not available | - | missing: receivables, ppe, depreciation, sga, total_debt, receivables_prev, gross_profit_prev, ppe_prev, depreciation_prev, sga_prev, total_assets_prev, total_debt_prev |
| Interest coverage | -0.8293 (severe) | 2 | ebit=-112700000.0000, interest_expense=135900000.0000 |
| Price volatility | 35.4454 (normal) | 0 | volatility_annualized_pct=35.4454, max_drawdown_pct=24.3721 |

## Things worth checking first

- Wetteri: interest expense 9.49M against total debt 1.74M looks inconsistent; if interest expense is mis-tagged, the interest-coverage flag (-0.48x) is wrong.
- OCI: HIGH comes only from interest coverage (EBIT negative, -0.83x); Altman GREY, Ohlson and Zmijewski are low.
- Prosegur Cash: Altman not available (retained earnings missing); CRITICAL rests on Ohlson+Zmijewski with liabilities/assets 0.92.
- Endur, Sentia: HIGH from one severe Altman (Endur) / several elevated models (Sentia); neither is severe on a second model.


---
# Revision 2 (2026-11-25, scope change): IFRS 16 leases and provisional Ohlson

## What changed and why
1. **Lease items are now extracted** from ESEF filings (new optional fields `lease_liabilities` = `ifrs-full:LeaseLiabilities`, or current + non-current; `lease_interest_expense` = `InterestExpenseOnLeaseLiabilities`; `interest_expense_basis` = which tag the interest figure came from). Additive only: no existing field, ledger or decision changed.
2. **Debt incl. leases** = borrowings + lease liabilities for non-US filers (US GAAP operating leases are not comparable and are left alone). It is shown as an input of the interest-coverage signal together with debt incl. leases / EBITDA. When borrowings are not tagged the figure is only the lease part, so it is a floor and is flagged.
3. **Interest coverage**: lease interest is added to the interest bill only when the interest figure came from the narrow `InterestExpense` tag (possible double count, flagged). When it came from `FinanceCosts` (all seven cases below) lease interest is already inside and nothing is added.
4. **TLTA / Altman / Zmijewski**: an IFRS filer's reported `Liabilities` total already includes lease liabilities, so TLTA does not change. It is only raised if the stored total is smaller than borrowings + leases (a data defect); no case below triggered it.
5. **Ohlson is labelled provisional**; its asset unit is a config value (`ohlson.asset_unit_usd`, default 1000 = USD thousands).

## Effect on the seven flagged cases (staging, data re-extracted from the filings caches)
No level changed. Reason: lease liabilities were already inside total liabilities, no case tags lease interest separately, and all seven take interest from `FinanceCosts`.

| ticker | level | lease liabilities | lease interest | debt incl. leases | interest used | coverage | debt incl. leases / EBITDA |
|---|---|---|---|---|---|---|---|
| WETTERI | CRITICAL | 36,271,000 | - | 38,011,000 | 9,486,000 | -0.48x | - |
| TES | CRITICAL | 27,643,000 | - | 35,400,000 | 23,247,000 | 0.84x | 0.87 |
| GAM | CRITICAL | 101,554,000 | - | 101,554,000 | 20,372,000 | 1.40x | 1.18 |
| CASH | CRITICAL | 98,974,000 | - | 98,974,000 | 61,292,000 | 3.53x | 0.28 |
| ENDUR | HIGH | 488,900,000 | - | 1,403,500,000 | 175,000,000 | 1.84x | 2.14 |
| SNTIA | HIGH | 197,000,000 | - | 197,000,000 | 11,000,000 | 52.36x | - |
| OCI | HIGH | 93,300,000 | - | 93,300,000 | 135,900,000 | -0.83x | - |

Notes: Wetteri's debt (1.74M) looked tiny next to 9.5M of finance costs; with leases (36.3M) debt incl. leases is 38.0M, which explains part of the gap (the rest is other finance costs). GAM, Prosegur, Sentia and OCI do not tag borrowings, so their debt incl. leases is a floor, not total debt. Only Tesmec and Endur have both items (leverage 0.87x and 2.14x EBITDA).

## Ohlson O-score distribution in the staging sample (63 stocks with an O-score; unit = USD thousands, provisional)
| statistic | P(bankruptcy) |
|---|---|
| min / p10 / p25 | 0.000 / 0.003 / 0.022 |
| median | 0.075 |
| p75 / p90 / p95 | 0.191 / 0.348 / 0.518 |
| max | 0.667 |

Share of the sample at or above a cut-off: 0.038 (Ohlson's own) 67% (42 of 63); 0.10 44%; 0.25 16% (10); 0.35 10% (6); 0.50 6% (4). Ohlson's 0.038 flags two thirds of listed European/US stocks, so it cannot be used as an alert here.

**Sensitivity to the unconfirmed asset unit** (same 63 stocks): unit = USD gives median 0.005 and nobody above 0.25; USD thousands (default) gives median 0.075 and 10 above 0.25; USD millions gives median 0.575 and 48 above 0.25. Only the thousands reading gives a sensible spread, which is the evidence for the default, but it is not a confirmation.

**Proposed thresholds (calibrated to the data distribution, not to defaults): elevated 0.35, severe 0.50.** That flags about the top 10% as elevated and 6% as severe, matches the Zmijewski limits (0.35 / 0.50) so the two models speak the same language, and keeps the current severe value. The current elevated value 0.25 flags 16%. Caveats: this is a percentile calibration, not an outcome calibration (the sample has no default labels); the coefficients are from 1970s US industrial firms; and every number moves with the asset unit. Nothing was changed: the config still holds 0.50 / 0.25 until you decide.

## Revision 3 (2026-11-25, owner decision): Ohlson thresholds 0.35 / 0.50 (provisional)
Config now holds Ohlson elevated 0.35 and severe 0.50 (the "provisional" label stays until the asset unit is confirmed from Ohlson 1980). Staging re-run on the same 96 stocks: LOW 39 (+1), MEDIUM 23 (-1), HIGH 3, CRITICAL 4, no level 27. The only stock whose level changed is GB:LSE ECEL (MEDIUM to LOW; O-score probability 0.32, now below 0.35). None of the 7 flagged CRITICAL/HIGH cases changed.
