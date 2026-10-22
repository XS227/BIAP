# GB/LSE: 101 unresolved evidence cases — frozen audit scope

Audit: 18 October 2026 GB/LSE read-only full-universe audit; report prepared 23 October 2026. Source: docs/market-audit/research/2026-10-18/GB__LSE.audit.json.
Original result: 527 instruments; 421 evidence PASS, 105 evidence BLOCK, one API failure. Five code defects (CAN RAT RGL RBW 1SN) are excluded from this 101-item *follow-up scope* but their successful deployment is NOT established.
101 listings with 101 distinct ISINs correspond to only 97 issuer names; entries are not 101 uniquely verified operating companies.
No deployment or source-data re-analysis is claimed here. All statuses are dated. Preserve previous data.

## Classification rules

- EXCLUDE_CANDIDATE: named investment company, fund, VCT, investment preference/share class. Verify official listing/CFI before excluding.
- REVIEW_STRUCTURE: REIT/property company/investment holding or similar structure; do not automatically exclude an operating REIT.
- CHECK_COMMON_EQUITY: no vehicle clue found from names; still requires official ordinary-equity verification.
- CABP/CABA/CABB and HAN/HANA and EJFI/EJFZ represent possible multi-class/share lines; match legal entity, ISIN and instrument type before counting unique issuers.
- For eligible rows only, investigate official evidence, never weaken PASS criteria to increase BUY.

## Source-defined root causes

| Dated audit reason | Count |
|---|---:|
| Newer annual report/final results only as PDF or RNS text (no iXBRL) | 50 |
| Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | 18 |
| No GLEIF LEI for the ISIN (identity cannot be proven) | 18 |
| LEI known, nothing on NSM | 7 |
| Latest tagged package is itself old/late (no newer filing yet) | 5 |
| Fiscal transition period >12 months (annual scoring deliberately blocked) | 2 |
| Newest tagged package embeds another entity's LEI (hard gate) | 1 |
| TOTAL | 101 |

## Exact 101-ticker scoped audit list

| Ticker | Audited name | ISIN | Dated blocker reason | Dated classifier | Instrument review |
|---|---|---|---|---|---|
| AEWU | AEW UK REIT PLC | GB00BWD24154 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | EXCLUDE_CANDIDATE |
| AIC | ACHILLES INVESTMENT COMPANY LIMITED | GG00BT3GKD08 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | COVERAGE_GAP | EXCLUDE_CANDIDATE |
| AIRC | AIR CHINA LD | CNE1000001S0 | No GLEIF LEI for the ISIN (identity cannot be proven) | COVERAGE_GAP | CHECK_COMMON_EQUITY |
| ALNA | ALINA HOLDINGS PLC | GB00B1VS7G47 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | REVIEW_STRUCTURE |
| ALRT | DEFENCE HOLDINGS PLC | GB00BMWVF760 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| ALTR | ALT RESOURCES PLC | GB00BNVSX371 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | COVERAGE_GAP | CHECK_COMMON_EQUITY |
| AMC | AIRTEL MOBILE COMMERCE N.V. | NL0015074C60 | LEI known, nothing on NSM | COVERAGE_GAP | CHECK_COMMON_EQUITY |
| AMG | ATLAS METALS GROUP PLC | GB00BS2GR553 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| AMGO | AMIGO RESOURCES PLC | GB00BFFK8T45 | Fiscal transition period >12 months (annual scoring deliberately blocked) | PIPELINE_FAILURE | CHECK_COMMON_EQUITY |
| AMOI | ANEMOI INTERNATIONAL LTD | VGG0419A1057 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| AMRQ | AMAROQ LTD. | CA02311U1030 | No GLEIF LEI for the ISIN (identity cannot be proven) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| BRES | BLENCOWE RESOURCES PLC | GB00BFCMVS34 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| BSFA | BSF ENTERPRISE PLC | GB00BHNBDQ51 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| BVC | BATM ADVANCED COMMUNICATIONS LD | IL0010849045 | No GLEIF LEI for the ISIN (identity cannot be proven) | INDEX_LAG | CHECK_COMMON_EQUITY |
| BYG | BIG YELLOW GROUP PLC | GB0002869419 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| CABA | CAB PAYMENTS HOLDINGS PLC | GB00BV894922 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | LEGIT_OFFICIAL_STALE | CHECK_COMMON_EQUITY |
| CABB | CAB PAYMENTS HOLDINGS PLC | GB00BV88ZY11 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | LEGIT_OFFICIAL_STALE | CHECK_COMMON_EQUITY |
| CABP | CAB PAYMENTS HOLDINGS PLC | GB00BMCYKB41 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| CGEO | GEORGIA CAPITAL PLC | GB00BF4HYV08 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | REVIEW_STRUCTURE |
| CHF | CHESTERFIELD RESOURCES PLC | GB00BF2F1X78 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| CHLL | CHILL BRANDS GROUP PLC | GB00BX017R92 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| CIZ | CIZZLE BIOTECHNOLOGY HOLDINGS PLC | GB00BNG2VN02 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| COBR | COBRA RESOURCES PLC | GB00BGJW5255 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| CYKL | CYKEL AI PLC | GB00BQYLVW97 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| DAT | DATANG INTERNATIONAL POWER GENERATION COMPANY LD | CNE1000002Z3 | No GLEIF LEI for the ISIN (identity cannot be proven) | COVERAGE_GAP | CHECK_COMMON_EQUITY |
| DATA | GLOBALDATA PLC | GB00BR3VDF43 | LEI known, nothing on NSM | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| DISH | AMALA FOODS PLC | JE00BG12QT70 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| DVT | DAVICTUS PLC | JE00BYY5RQ34 | Latest tagged package is itself old/late (no newer filing yet) | LEGIT_OFFICIAL_STALE | CHECK_COMMON_EQUITY |
| ECOR | ECORA ROYALTIES PLC | GB0006449366 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| EDV | ENDEAVOUR MINING PLC | GB00BL6K5J42 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| EJFI | EJF INVESTMENTS LTD | JE00BF0D1M25 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | EXCLUDE_CANDIDATE |
| EJFZ | EJF INVESTMENTS LTD | JE00BRZSNL95 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | COVERAGE_GAP | EXCLUDE_CANDIDATE |
| ESNT | ESSENTRA PLC | GB00B0744359 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| EVR | EVRAZ PLC | GB00B71N6K86 | Latest tagged package is itself old/late (no newer filing yet) | LEGIT_OFFICIAL_STALE | CHECK_COMMON_EQUITY |
| EVST | EVEREST GLOBAL PLC | GB00BVD9DK18 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_STALE | CHECK_COMMON_EQUITY |
| FDM | FDM GROUP (HOLDINGS) PLC | GB00BLWDVP51 | LEI known, nothing on NSM | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| FWT | FORESIGHT TECHNOLOGY VCT PLC | GB00BKF2JH04 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | EXCLUDE_CANDIDATE |
| GEMR | GEM RESOURCES PLC | GB00BL979W39 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| GEX | GEORGINA ENERGY PLC | GB00BSMN5L80 | LEI known, nothing on NSM | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| GR1T | GRIT REAL ESTATE INCOME GROUP LIMITED | GG00BMDHST63 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | REVIEW_STRUCTURE |
| GSCU | GREAT SOUTHERN COPPER PLC | GB00BLB5BF24 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_STALE | CHECK_COMMON_EQUITY |
| HAMA | HAMAK STRATEGY LIMITED | VGG4256S1048 | No GLEIF LEI for the ISIN (identity cannot be proven) | LEGIT_OFFICIAL_UNAVAILABLE | REVIEW_STRUCTURE |
| HAN | HANSA INVESTMENT COMPANY LIMITED | BMG428941162 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | EXCLUDE_CANDIDATE |
| HANA | HANSA INVESTMENT COMPANY LIMITED | BMG428941089 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | EXCLUDE_CANDIDATE |
| HELD | HELLENIC DYNAMICS PLC | GB00BRXCFB77 | Latest tagged package is itself old/late (no newer filing yet) | PIPELINE_FAILURE | CHECK_COMMON_EQUITY |
| HEMO | HEMOGENYX PHARMACEUTICALS PLC | GB00BQVXM815 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| HID | HIDONG ESTATE PLC | GB0004251863 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | COVERAGE_GAP | REVIEW_STRUCTURE |
| HREE | HARENA RARE EARTHS PLC | GB00BMGRFP88 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| HUI | HYDROGEN UTOPIA INTERNATIONAL PLC | GB00BMFR8J48 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| IBAI | IMAGING BIOMETRICS LIMITED | JE00BD4H0R42 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| IGG | IG GROUP HOLDINGS PLC | GB00B06QFB75 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| IHP | INTEGRAFIN HOLDINGS PLC | GB00BD45SH49 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| IMC | IMC EXPLORATION GROUP PLC | IE00B6WC2H62 | No GLEIF LEI for the ISIN (identity cannot be proven) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| IWG | INTERNATIONAL WORKPLACE GROUP PLC | JE00BYVQYS01 | Latest tagged package is itself old/late (no newer filing yet) | INDEX_LAG | CHECK_COMMON_EQUITY |
| KAKU | KAKUZI LD | KE0000000281 | No GLEIF LEI for the ISIN (identity cannot be proven) | PIPELINE_FAILURE | CHECK_COMMON_EQUITY |
| KLSO | KELSO GROUP HOLDINGS PLC | GB00BK1VJS23 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | REVIEW_STRUCTURE |
| KNB | KANABO GROUP PLC | GB00BYQCS703 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| KR1 | KR1 PLC | IM00BYYPQX37 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | REVIEW_STRUCTURE |
| MAB1 | MORTGAGE ADVICE BUREAU (HOLDINGS) PLC | GB00BQSBH502 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| MACF | MACFARLANE GROUP PLC | GB0005518872 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| MCG | MOBICO GROUP PLC | GB0006215205 | Fiscal transition period >12 months (annual scoring deliberately blocked) | PIPELINE_FAILURE | CHECK_COMMON_EQUITY |
| MILA | MILA RESOURCES PLC | GB00BD4FCK53 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| MNO | MERIDIAN MINING PLC | GB00BVPND783 | LEI known, nothing on NSM | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| MNTL | TECHNOLOGY MINERALS PLC | GB00BWYF7709 | Newest tagged package embeds another entity's LEI (hard gate) | INDEX_LAG | CHECK_COMMON_EQUITY |
| MOH | MOH NIPPON PLC | GB00BMYX7295 | LEI known, nothing on NSM | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| NANO | NANOCO GROUP PLC | GB00B01JLR99 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| NARF | NARF INDUSTRIES PLC | GB00BMH18M70 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | PIPELINE_FAILURE | CHECK_COMMON_EQUITY |
| NFM | NEW FRONTIER MINERALS LIMITED | AU0000368748 | No GLEIF LEI for the ISIN (identity cannot be proven) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| NFX | NUFORMIX PLC | GB00BYW79Y38 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| NXR | NORCROS PLC | GB00BYYJL418 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| OMU | OLD MUTUAL LIMITED | ZAE000255360 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| ONDO | ONDO INSURTECH PLC | GB00BNVVGD77 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| PAF | PAN AFRICAN RESOURCES PLC | GB0004300496 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| PCA | PALACE CAPITAL PLC | GB00BF5SGF06 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | REVIEW_STRUCTURE |
| PHP | PRIMARY HEALTH PROPERTIES PLC | GB00BYRJ5J14 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | REVIEW_STRUCTURE |
| PRE | PENSANA PLC | GB00BKM0ZJ18 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| PTEC | PLAYTECH PLC | IM00B7S9G985 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| PYX | PYX RESOURCES LIMITED | AU0000078487 | No GLEIF LEI for the ISIN (identity cannot be proven) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| ROSE | ROSEBANK INDUSTRIES PLC | JE00BSBJ5M88 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | REVIEW_STRUCTURE |
| RSG | RESOLUTE MINING LIMITED | AU000000RSG6 | No GLEIF LEI for the ISIN (identity cannot be proven) | INDEX_LAG | CHECK_COMMON_EQUITY |
| SEFA | SHEFA GEMS LTD | IL0011101057 | No GLEIF LEI for the ISIN (identity cannot be proven) | PIPELINE_FAILURE | CHECK_COMMON_EQUITY |
| SIGC | SHERBORNE INVESTORS (GUERNSEY) C LIMITED | GG00BZ3C3B94 | Newest annual report lodged "Untagged" (pdf2htmlEX/HTML, no iXBRL) | INDEX_LAG | EXCLUDE_CANDIDATE |
| SRE | SIRIUS REAL ESTATE LD | GG00B1W3VF54 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | REVIEW_STRUCTURE |
| SYME | SUPPLY@ME CAPITAL PLC | GB00BFMDJC60 | Latest tagged package is itself old/late (no newer filing yet) | COVERAGE_GAP | CHECK_COMMON_EQUITY |
| THAL | THALASSA HOLDINGS LIMITED | VGG878801114 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | REVIEW_STRUCTURE |
| TKO | TREKOR METALS LIMITED | CA89472Y1079 | No GLEIF LEI for the ISIN (identity cannot be proven) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| TNE | TECHNOLOGIES NEW ENERGY PLC | GB00BNVRHQ51 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| UMR | UNICORN MINERAL RESOURCES PLC | IE000H00V4G5 | No GLEIF LEI for the ISIN (identity cannot be proven) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| UPL | UPLAND RESOURCES LIMITED | JE00BJXN4P16 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| VALT | VALTERRA PLATINUM LIMITED | ZAE000013181 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| VLX | VOLEX PLC | GB0009390070 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| VOX | VOX VALOR CAPITAL LIMITED | KYG9507A1094 | No GLEIF LEI for the ISIN (identity cannot be proven) | PIPELINE_FAILURE | CHECK_COMMON_EQUITY |
| VP. | VP PLC | GB0009286963 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| WCAT | WILDCAT GOLD PLC | GB00BMQC7357 | No GLEIF LEI for the ISIN (identity cannot be proven) | PIPELINE_FAILURE | CHECK_COMMON_EQUITY |
| WGP | WORLDLINK GROUP PLC | GB00B3P21X12 | LEI known, nothing on NSM | COVERAGE_GAP | CHECK_COMMON_EQUITY |
| WISE | WISE GROUP PLC | JE00BQKY0816 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| WRN | WORTHINGTON GROUP PLC | GB00B01YQ796 | No GLEIF LEI for the ISIN (identity cannot be proven) | COVERAGE_GAP | CHECK_COMMON_EQUITY |
| ZAIM | ADALAN VENTURES PLC | GB00BMXTZ463 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | CHECK_COMMON_EQUITY |
| ZEG | ZEGONA COMMUNICATIONS PLC | GB00BVGBY890 | Newer annual report/final results only as PDF or RNS text (no iXBRL) | INDEX_LAG | REVIEW_STRUCTURE |
| ZEN | ZENITH ENERGY LTD. | CA98936C8584 | No GLEIF LEI for the ISIN (identity cannot be proven) | LEGIT_OFFICIAL_UNAVAILABLE | CHECK_COMMON_EQUITY |
| ZOYO | ZOYO LIMITED | KYG4598W1024 | No GLEIF LEI for the ISIN (identity cannot be proven) | PIPELINE_FAILURE | CHECK_COMMON_EQUITY |

## Follow-up acceptance criteria

1. Review ONLY these 101 ticker+ISIN pairs and only GB/LSE. Do not scan entire venue or other countries. Verify official instrument type and the original root-cause evidence with primary-source URLs.
2. For eligible companies, independently verify filing period, issuer LEI/ISIN, currency, fiscal duration and published statements. Missing official evidence stays BLOCK. No AI-generated accounting figures.
3. Output an updated per-symbol audit with old/new evidence status, official URL, filing period, instrument classification, exclusion reason if any, and source timestamp. Report PASS/BLOCK changes separately from eligibility removals.
4. Do not change BUY thresholds, historical snapshots, production services, or other exchanges. Use a research branch only; no merge or deploy.

## Out-of-scope five code fixes

CAN (FCA NSM fallback), RAT (.xbri parser), RGL/RBW (PBT-tax extraction), 1SN (digit-leading ticker). Neither their patch nor their production verification is part of this review.

Reproduction: filter the audit JSON for evidence not PASS, excluding CAN RAT RGL RBW 1SN; assert there are exactly 101.
