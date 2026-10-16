<!-- UPDATE7 -->
# BIAP Global country validation - refreshed 2026-10-16 (Update 7)

- **Code validated:** `1da5cd69e12955d2363a9f16fd26a29824b7218e` (PR #52 head, `feat/global-evidence-signals`). Working tree clean. PR #54 head is `5671891d51ec3b6e322eb7e2aef693d179af24b9` (`fix/mobile-ios-icon-schema`, mobile-only; not part of this runtime validation).
- **Test window (UTC):** 2026-10-16T10:37:08Z .. 10:42:39Z. Re-run of all seven countries, 176 companies (US 26, GB/FR/IT/SE/NO/DE 25 each), top by market cap from each exchange's deep-scan cache.
- **Mode:** non-destructive, in-process API (`/global/instruments`, `/global/analyze`) with `BIAP_GLOBAL_ONLINE_FIRST=1` and `BIAP_GLOBAL_US_ISIN_RESOLVE=1` against an **isolated copy** of the production data (`/home/ubuntu/biap-validation-20261016/data-u7`, read from `/var/lib/biap-global`; no ESEF `esef/` or `sec-edgar` archives copied). No bulk downloads, no merge, no deploy, no service restart. A fingerprint (path/size/mtime) of production `scan-cache/` taken before and after the run is identical.
- **Tests:** full `pytest analysis/tests` on `1da5cd6`: **1442 passed, 0 failed** (87.7 s). Update 6 only re-ran 16 tests; the 1439 figure was measured on `4a906e9`.

## How to read the numbers: verified vs estimated vs cached

| Class | What it covers in this report |
|---|---|
| **Verified** | Fundamentals read from official filings (SEC EDGAR, ESEF/OAM, FCA NSM) with provenance `independently_verified`; evidence gates PASS/WARN/BLOCK; ISINs resolved from an official/open source (listing data, GLEIF, OpenFIGI); a **verified BUY_CANDIDATE** = call BUY_CANDIDATE **and** evidence PASS **and** governance ACCEPT **and** distress LOW_RISK **and** same-sector peer group >= 8 **and** peer scan state `ok` (the BUY governance rules of commit 4a906e9). |
| **Estimated** | Relative P/E vs same-sector scan median, calibrated confidence, forecast/quality/risk agent votes, distress category, and the US ISIN coverage from the flag-gated resolver (measured only in the isolated run; the production flag is not enabled). These are model outputs, not facts. |
| **Cached** | Everything is cached provider data, not live quotes: prices are 1.9-3.2 days old, annual figures are FY2025 (period end 2025-12-31, median 289 days old), and the peer benchmarks come from persisted scan caches (13 h old for six markets, 0.8 h for Germany). Nothing here is a live quote. |

## Summary (all 176 companies analysed, 0 errors, 0 lookup failures, 0 degraded providers)

| Country | Sampled | Evidence P/W/B | Verified BUY | Other BUY | REVIEW | ABSTAIN | No price | ISIN issues | Price age med/max | Peer benchmark (cachedAt -> expires) | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| US | 26 | 26/0/0 | 0 (-) | 0 | 21 | 0 | 0 | 4 missing (AMZN, ASML, ETN, KO) | 1.9d / 2.9d | 2026-10-15T21:42-21:43Z -> 2026-10-16T21:42Z | WARN |
| GB | 25 | 25/0/0 | 1 (BHP) | 0 | 16 | 0 | 0 | 0 | 2.2d / 3.2d | 2026-10-15T21:44Z -> 2026-10-16T21:44Z | PASS |
| FR | 25 | 25/0/0 | 0 (-) | 0 | 16 | 0 | 0 | 0 | 2.2d / 3.2d | 2026-10-15T21:45Z -> 2026-10-16T21:45Z | PASS |
| IT | 25 | 22/0/3 | 1 (PIRC) | 0 | 16 | 4 | 0 | 0 | 2.2d / 3.2d | 2026-10-15T21:46Z -> 2026-10-16T21:46Z | WARN |
| SE | 25 | 25/0/0 | 0 (-) | 0 | 19 | 2 | 0 | 0 | 3.2d / 3.2d | 2026-10-15T21:44Z -> 2026-10-16T21:44Z | PASS |
| NO | 25 | 25/0/0 | 1 (HAUTO) | 0 | 16 | 0 | 0 | 0 | 2.2d / 3.2d | 2026-10-15T21:44Z -> 2026-10-16T21:44Z | WARN |
| DE | 25 | 21/4/0 | 0 (-) | 0 | 23 | 0 | 0 | 0 | 3.2d / 3.2d | 2026-10-16T09:57:37Z -> 2026-10-17T09:57Z (timer 09:57:22Z) | WARN |

Status rule (unchanged): BLOCK = >20% of sample evidence-blocked/no coverage; WARN = any evidence BLOCK/WARN name, non-fresh peer benchmark, BUY share >30%, or missing ISIN/price; else PASS. US is WARN only because 4 ISINs are unresolved; GB/FR/SE are PASS on evidence, but see defect D1 (their benchmarks expire tonight). `REVIEW`/`ABSTAIN` are governance actions; `ACCEPT` = the remainder (call is a stated HOLD_OR_WATCH or BUY).

### Calls per country

| Country | BUY_CANDIDATE | HOLD_OR_WATCH | NO_RECOMMENDATION | Fail-closed BUY (benchmark unavailable) |
|---|---|---|---|---|
| US | 0 | 5 | 21 | - |
| GB | 1 | 8 | 16 | - |
| FR | 0 | 9 | 16 | - |
| IT | 1 | 4 | 20 | - |
| SE | 0 | 4 | 21 | - |
| NO | 1 | 8 | 16 | MEDI |
| DE | 0 | 2 | 23 | - |

## Per-country detail

### USA (NASDAQ+NYSE) - WARN

- Evidence 26/26 PASS (SEC EDGAR). Calls: 5 HOLD_OR_WATCH, 21 NO_RECOMMENDATION; no BUY.
- ISIN: 22/26 resolved by the GLEIF + OpenFIGI resolver (licence-clean), **4 unresolved: AMZN, ASML, ETN, KO** (ambiguous/no match returns no ISIN by design). Analysis is unaffected. This is an **estimate of coverage measured in the isolated run**; production has the flag off, so production still reports 26/26 missing until a deploy approval turns it on.
- Fundamentals: FY period ends median 289 d / max 384 d old; prices 1.9 d / 2.9 d.
- Annual period age median/max: 289 d / 384 d (n=26). Distress: {'ELEVATED_RISK': 2, 'LOW_RISK': 16, 'INSUFFICIENT_DATA': 7, 'HIGH_RISK': 1}.

### UK (LSE) - PASS

- Evidence 25/25 PASS (FCA NSM / OAM official). **Verified BUY_CANDIDATE: BHP** (conf 0.67, distress LOW_RISK, 10 same-sector peers, 6 agents positive except comparison -0.3 so it is not P/E-only).
- RIO moved HOLD_OR_WATCH -> NO_RECOMMENDATION vs the 02:57Z run: calibrated confidence 0.531 is below the 0.55 accept threshold (scan benchmark refreshed 2026-10-15 21:44Z); no defect.
- Annual period age median/max: 289 d / 398 d (n=25). Distress: {'LOW_RISK': 9, 'ELEVATED_RISK': 5, 'INSUFFICIENT_DATA': 8, 'HIGH_RISK': 2, 'NOT_APPLICABLE': 1}.

### France (Euronext Paris) - PASS

- Evidence 25/25 PASS (ESEF). 9 HOLD_OR_WATCH, 16 NO_RECOMMENDATION; no BUY. Distress: 6 HIGH_RISK names in the sample (not BUY-eligible by rule).
- Annual period age median/max: 289 d / 411 d (n=25). Distress: {'NOT_APPLICABLE': 4, 'INSUFFICIENT_DATA': 8, 'HIGH_RISK': 6, 'LOW_RISK': 4, 'ELEVATED_RISK': 3}.

### Italy (Euronext Milan) - WARN

- Evidence 22 PASS / 3 BLOCK, all three fail-closed and **unchanged since Update 5**: A2A (parent ESEF not available: the packages found belong to A2A Energia S.p.A.), MB (Mediobanca, 6-month transition-period ESEF, never annualised), REC (Recordati, 1-day duration contexts, filer defect). Governance ABSTAIN on all three; a fourth ABSTAIN, G (Generali), is a low-confidence (0.33) abstention with evidence PASS.
- **Verified BUY_CANDIDATE: PIRC (Pirelli).** The Update 5 open item is now confirmed live under the BUY governance rule: distress LOW_RISK, 22 same-sector peers (rule needs >= 8), evidence coverage 0.94, call stays BUY_CANDIDATE. Borderline: calibrated confidence **0.5502 vs the 0.55 accept threshold**; comparison vote 0.0, so valuation is neutral and the call rests on fundamental/quality votes.
- Italy remains an evidence WARN market for as long as the three source defects exist; no official filing that would unblock them was found since Update 5 (no new retrieval was attempted: non-bulk, read-only run).
- Annual period age median/max: 289 d / 289 d (n=25). Distress: {'ELEVATED_RISK': 2, 'NOT_APPLICABLE': 12, 'LOW_RISK': 4, 'INSUFFICIENT_DATA': 5, 'HIGH_RISK': 2}.

### Sweden (Nasdaq Stockholm) - PASS

- Evidence 25/25 PASS. 4 HOLD_OR_WATCH, 21 NO_RECOMMENDATION, **no BUY** (SKA.B was BUY_CANDIDATE in the 02:57Z run, now HOLD_OR_WATCH at confidence 0.5503 after the benchmark refresh; ALFA, ASSA.B, ERIC.A, ERIC.B moved HOLD -> NO_RECOMMENDATION). 2 ABSTAIN (INDU.A, INDU.C: confidence 0.34).
- Fundamentals period median 289 d, max 320 d.
- Annual period age median/max: 289 d / 320 d (n=25). Distress: {'LOW_RISK': 14, 'ELEVATED_RISK': 2, 'INSUFFICIENT_DATA': 5, 'NOT_APPLICABLE': 4}.

### Norway (Euronext Oslo) - WARN

- Evidence 25/25 PASS. **The 10 BUY_CANDIDATEs of the 02:57Z run are now measured live (previously derived from the audit table):** AKSO, BNOR, SNTIA -> REVIEW (ELEVATED_RISK distress); DOFG, SOFF, SOMA -> REVIEW (distress INSUFFICIENT_DATA); EPR -> REVIEW (peer group 5 < 8); MOWI -> REVIEW (confidence 0.51 < 0.55); YAR -> HOLD_OR_WATCH; **HAUTO remains BUY_CANDIDATE** (verified: LOW_RISK, 29 peers, conf 0.63, not P/E-only: comparison +0.6, quality +0.65, forecast +0.2). Caveat from the earlier audit still applies to HAUTO: fundamental vote is slightly negative (-0.05) and it trades at an extreme P/E discount (6.8 vs 17.6), likely one-off or cyclical earnings; it uses 289-day-old annual figures. Treat as an analyst-review item, not a clean BUY.
- MEDI: fail-closed (valuation benchmark unavailable for its sector, peer group < 8) -> NO_RECOMMENDATION. BUY share is now 1/25 (4%), below the 30% concentration warning, so the earlier concentration finding is **resolved** by the implemented rule.
- Status WARN solely because of the freshness defect D1 and the single HAUTO caveat; there is no evidence BLOCK/WARN.
- Annual period age median/max: 289 d / 289 d (n=25). Distress: {'NOT_APPLICABLE': 3, 'ELEVATED_RISK': 4, 'LOW_RISK': 11, 'INSUFFICIENT_DATA': 5, 'HIGH_RISK': 2}.

### Germany (Xetra) - WARN

- Evidence 21 PASS / 4 WARN / 0 BLOCK. WARN names (CBK, HNR1, MUV2, TLX) have no official fundamentals source: CBK and TLX are fail-closed because the SEC ticker lookup returned a different issuer (Commercial Bancgroup Inc., Telix Pharmaceuticals) - correctly rejected; HNR1 and MUV2 have no SEC CIK. All four are NO_RECOMMENDATION. No BUY; 2 HOLD_OR_WATCH. (Update 5 had 23 PASS / 2 WARN: the extra two WARNs are HNR1 and TLX; their calls did not change.)
- Peer benchmark `XETRA.json` cachedAt 2026-10-16T09:57:37Z (timer-produced; 150 rows) -> state `ok` for 25/25. The systemd timer `biap-global-de-benchmark.timer` is enabled and last result `success`; next run 2026-10-17T09:57:22Z.
- Fundamentals: 14/25 carry a period age (median 289 d, max 381 d); 11 have PERIOD_UNKNOWN (share-count/benchmark based). Prices 3.2 d old (with Sweden, the oldest of the seven).
- Annual period age median/max: 289 d / 381 d (n=14). Distress: {'NOT_APPLICABLE': 7, 'LOW_RISK': 4, 'ELEVATED_RISK': 8, 'INSUFFICIENT_DATA': 6}.

## Unresolved defects and risks

| # | Defect | Impact | Owner decision needed |
|---|---|---|---|
| D1 | **Peer benchmarks of US, GB, FR, IT, SE, NO expire 2026-10-16 ~21:42-21:46Z** (hard 24 h limit, `service._scan_peer_state`; cachedAt 2026-10-15 21:42-21:46Z). Only Germany has a refresh timer. | After expiry all valuation comparisons fail closed: BHP, PIRC, HAUTO -> NO_RECOMMENDATION, MEDI-style 'benchmark unavailable' reasons across the six markets, until a scan is run. Safe (fail-closed), but the BUY results above are time-limited to roughly 11 hours from this run. | Approve a bounded controlled refresh (or extending the DE-style timer to the other six markets). Not done here: no scans, no timers. |
| D2 | Germany timer margin: cache expires 09:57:37Z (24 h after cachedAt) but the timer fires at 09:57:22Z +/- 1 min `AccuracySec` and takes ~15 s, so there is **0-60 s of fail-closed time every day** and any run slip beyond 24 h makes DE fail closed. Update 6 stated a 30 h window; that is the scan-read limit, the peer-benchmark limit is 24 h. | Daily sub-minute (worst case longer) window with no DE benchmark. | Shorten the cadence (e.g. 20 h) in `deploy/systemd`; requires a code change + approved timer re-install. Not changed here. |
| D3 | Italy A2A / Recordati / Mediobanca evidence BLOCK (source defects, see Appendix). | 3/25 fail-closed; correct. | Parent ESEF from OAM 1INFO; corrected Recordati package; Mediobanca stays blocked until a 12-month statement exists. |
| D4 | US ISIN coverage: resolver flag off in production; 4/26 unresolved even with it on. | ISIN shown as missing for all 26 in production today; analysis unaffected. | Approval to enable `BIAP_GLOBAL_US_ISIN_RESOLVE` at deploy. |
| D5 | Germany: 4 names with no official fundamentals source (CBK, HNR1, MUV2, TLX); 11 with unknown period. | Fail-closed NO_RECOMMENDATION. | None required; improvement item. |
| D6 | Price and fundamentals age: prices 1.9-3.2 d, annual figures 289 d median (FY2025; no interim/TTM evidence outside US/DE). | Cached, not live. Reported honestly in every row. | Interim evidence for non-US markets is future work. |
| D7 | Borderline results: PIRC confidence 0.5502 vs 0.55; SKA.B 0.5503; RIO 0.531. | Calls can flip on a data refresh. | None; review before presenting. |

Closed since Update 5: Norway BUY concentration (10 -> 1, measured live); PIRC post-rule status (confirmed BUY); DE timer installed and verified (Update 5/6 comments on PR #52); full suite re-run (1442 passed).

## CI status of the PR heads (checked 2026-10-16 ~10:35Z)

| PR | Head | backend | global-backend | android-bundle | typecheck | android-installable-apk / build-apk |
|---|---|---|---|---|---|---|
| #52 | `1da5cd6` | [success](https://github.com/XS227/BIAP/actions/runs/38886053930/job/116923937987) | [success](https://github.com/XS227/BIAP/actions/runs/38886053919/job/116923937323) | [success](https://github.com/XS227/BIAP/actions/runs/38886053930/job/116923937274) | - | skipped ([job](https://github.com/XS227/BIAP/actions/runs/38886053930/job/116923939144)) |
| #54 | `5671891` | [success](https://github.com/XS227/BIAP/actions/runs/38838152170/job/116771806242) | - | [success](https://github.com/XS227/BIAP/actions/runs/38838152170/job/116771806112) | [success](https://github.com/XS227/BIAP/actions/runs/38838152191/job/116771806733) | skipped (PR runs) |

No branch protection on `main`, so no check is formally 'required'. Both heads are unchanged since Update 6. Mergeable: both `MERGEABLE`; #54 is a draft.

## GO / NO-GO

**PR #52 - NO-GO for merge today (technically ready).** CI is green, 1442 tests pass, BUY governance verified live (of the 10 Norwegian BUYs, 8 routed to REVIEW, 1 to HOLD_OR_WATCH, 1 (HAUTO) stays BUY; PIRC confirmed), Italy fails closed correctly, and nothing regressed in seven countries. Merging is nevertheless a deploy action: the diff touches `analysis/**` and `deploy/systemd/**`, which are path triggers of `deploy-backend.yml` on push to `main`. It becomes GO when (1) the owner explicitly approves a production deploy window, and (2) D1 is decided (refresh or timer for the six non-DE markets) so that the BUY results do not silently fail closed hours after the deploy, and ideally (3) D2 cadence is shortened.

**PR #54 - NO-GO for merge today (technically ready).** Draft, mergeable, CI green on `5671891` (backend, android-bundle, typecheck). It is a one-line mobile schema fix (`ios.icon`) with no runtime effect on the analysis engine, but merging touches `mobile/**`, which triggers Expo EAS build and (via `workflow_run`) the backend deploy workflow. GO once the deploy window is approved; merge after or together with #52's window, not before.

Nothing was merged, deployed, restarted or downloaded in bulk. Preserved untouched: historical company data, ESEF archives, DMA agents, rollback snapshots (`backup-*`, `*.prev`), the other session's `/dev/shm/val-20261016c` copy.

## Per-company results (this run)

**US** - ticker: call / evidence / governance / confidence

| Ticker | Call | Ev | Gov | Conf | Price | ISIN |
|---|---|---|---|---|---|---|
| AAPL | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 342.0 USD | US0378331005 |
| AMD | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 570.8200073242188 USD | US0079031078 |
| AMZN | NO_RECOMMENDATION | PASS | REVIEW | 0.64 | 254.0800018310547 USD | - |
| ASML | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 1717.760009765625 USD | - |
| AVGO | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 346.25 USD | US11135F1012 |
| COST | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 982.0 USD | US22160K1051 |
| CSCO | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 113.63999938964844 USD | US17275R1023 |
| GOOG | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 349.5199890136719 USD | US02079K1079 |
| GOOGL | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 347.6400146484375 USD | US02079K3059 |
| MSFT | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 533.6900024414062 USD | US5949181045 |
| MU | NO_RECOMMENDATION | PASS | REVIEW | 0.7 | 953.1900024414062 USD | US5951121038 |
| NVDA | NO_RECOMMENDATION | PASS | REVIEW | 0.64 | 221.3000030517578 USD | US67066G1040 |
| PLTR | NO_RECOMMENDATION | PASS | REVIEW | 0.64 | 208.6699981689453 USD | US69608A1088 |
| APH | NO_RECOMMENDATION | PASS | REVIEW | 0.64 | 85.88999938964844 USD | US0320951017 |
| DIS | HOLD_OR_WATCH | PASS | ACCEPT | 0.69 | 108.98999786376953 USD | US2546871060 |
| EMR | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 163.5 USD | US2910111044 |
| ETN | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 408.8500061035156 USD | - |
| JNJ | HOLD_OR_WATCH | PASS | ACCEPT | 0.69 | 253.91000366210938 USD | US4781601046 |
| KO | HOLD_OR_WATCH | PASS | ACCEPT | 0.58 | 91.77999877929688 USD | - |
| MRK | HOLD_OR_WATCH | PASS | ACCEPT | 0.69 | 147.3699951171875 USD | US58933Y1055 |
| NEM | NO_RECOMMENDATION | PASS | REVIEW | 0.64 | 115.58999633789062 USD | US6516391066 |
| PFE | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 28.3700008392334 USD | US7170811035 |
| PG | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 156.52999877929688 USD | US7427181091 |
| TJX | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 141.49000549316406 USD | US8725401090 |
| TMO | NO_RECOMMENDATION | PASS | REVIEW | 0.69 | 663.0399780273438 USD | US8835561023 |
| UBER | HOLD_OR_WATCH | PASS | ACCEPT | 0.69 | 71.31999969482422 USD | US90353T1007 |

**GB** - ticker: call / evidence / governance / confidence

| Ticker | Call | Ev | Gov | Conf | Price | ISIN |
|---|---|---|---|---|---|---|
| ABF | NO_RECOMMENDATION | PASS | REVIEW | 0.67 | 18.93 GBP | GB0006731235 |
| BATS | HOLD_OR_WATCH | PASS | ACCEPT | 0.6 | 42.25 GBP | GB0002875804 |
| BHP | BUY_CANDIDATE | PASS | ACCEPT | 0.67 | 32.05 GBP | AU000000BHP4 |
| BNZL | HOLD_OR_WATCH | PASS | ACCEPT | 0.67 | 27.8 GBP | GB00B0744B38 |
| CCEP | NO_RECOMMENDATION | PASS | REVIEW | 0.67 | 79.8 GBP | GB00BDCPN049 |
| CCH | HOLD_OR_WATCH | PASS | ACCEPT | 0.67 | 43.32 GBP | CH0198251305 |
| DPLM | NO_RECOMMENDATION | PASS | REVIEW | 0.6 | 79.35000000000001 GBP | GB0001826634 |
| EXPN | HOLD_OR_WATCH | PASS | ACCEPT | 0.6 | 27.196201171875 GBP | GB00B19NLV48 |
| FRES | NO_RECOMMENDATION | PASS | REVIEW | 0.67 | 27.16 GBP | GB00B2QPKJ12 |
| GSK | NO_RECOMMENDATION | PASS | REVIEW | 0.6 | 17.53 GBP | GB00BN7SWP63 |
| HLMA | NO_RECOMMENDATION | PASS | REVIEW | 0.67 | 34.96 GBP | GB0004052071 |
| HLN | NO_RECOMMENDATION | PASS | REVIEW | 0.67 | 3.573999938964844 GBP | GB00BMX86B70 |
| IAG | NO_RECOMMENDATION | PASS | REVIEW | 0.62 | 4.135660705566407 GBP | ES0177542018 |
| MKS | NO_RECOMMENDATION | PASS | REVIEW | 0.62 | 4.115899963378906 GBP | GB0031274896 |
| NWG | NO_RECOMMENDATION | PASS | REVIEW | 0.39 | 6.652000122070312 GBP | GB00BM8PJY71 |
| NXT | NO_RECOMMENDATION | PASS | REVIEW | 0.67 | 148.25 GBP | GB0032089863 |
| REL | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 27.71 GBP | GB00B2B0DG97 |
| RIO | NO_RECOMMENDATION | PASS | REVIEW | 0.53 | 69.97 GBP | GB0007188757 |
| RKT | HOLD_OR_WATCH | PASS | ACCEPT | 0.65 | 53.02 GBP | GB00BSZBP530 |
| RR. | HOLD_OR_WATCH | PASS | ACCEPT | 0.62 | 13.605999755859376 GBP | GB00B63H8491 |
| S32 | HOLD_OR_WATCH | PASS | ACCEPT | 0.67 | 2.503999938964844 GBP | AU000000S320 |
| SHEL | HOLD_OR_WATCH | PASS | ACCEPT | 0.6 | 38.655 GBP | GB00BP6MXD84 |
| SVT | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 31.69 GBP | GB00B1FH8J72 |
| TSCO | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 5.191719970703125 GBP | GB00BLGZ9862 |
| ULVR | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 47.105000000000004 GBP | GB00BVZK7T90 |

**FR** - ticker: call / evidence / governance / confidence

| Ticker | Call | Ev | Gov | Conf | Price | ISIN |
|---|---|---|---|---|---|---|
| ABCA | NO_RECOMMENDATION | PASS | REVIEW | 0.43 | 5.730000019073486 EUR | FR0004040608 |
| AC | HOLD_OR_WATCH | PASS | ACCEPT | 0.57 | 45.630001068115234 EUR | FR0000120404 |
| AF | NO_RECOMMENDATION | PASS | REVIEW | 0.62 | 10.555000305175781 EUR | FR001400J770 |
| BOI | HOLD_OR_WATCH | PASS | ACCEPT | 0.67 | 17.350000381469727 EUR | FR0000061129 |
| BUR | HOLD_OR_WATCH | PASS | ACCEPT | 0.65 | 324.0 EUR | FR0000061137 |
| CS | NO_RECOMMENDATION | PASS | REVIEW | 0.44 | 42.0099983215332 EUR | FR0000120628 |
| DEEZR | NO_RECOMMENDATION | PASS | REVIEW | 0.62 | 1.2949999570846558 EUR | FR001400AYG6 |
| FNAC | NO_RECOMMENDATION | PASS | REVIEW | 0.42 | 34.54999923706055 EUR | FR0011476928 |
| GTT | HOLD_OR_WATCH | PASS | ACCEPT | 0.57 | 215.8000030517578 EUR | FR0011726835 |
| HO | NO_RECOMMENDATION | PASS | REVIEW | 0.62 | 224.10000610351562 EUR | FR0000121329 |
| KOF | NO_RECOMMENDATION | PASS | REVIEW | 0.62 | 18.940000534057617 EUR | FR0004007813 |
| LIN | HOLD_OR_WATCH | PASS | ACCEPT | 0.62 | 50.20000076293945 EUR | FR0004156297 |
| LNA | NO_RECOMMENDATION | PASS | REVIEW | 0.57 | 23.799999237060547 EUR | FR0004170017 |
| NEX | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 131.89999389648438 EUR | FR0000044448 |
| OR | NO_RECOMMENDATION | PASS | REVIEW | 0.61 | 406.8500061035156 EUR | FR0000120321 |
| PEUG | NO_RECOMMENDATION | PASS | REVIEW | 0.54 | 53.79999923706055 EUR | FR0000064784 |
| PLX | NO_RECOMMENDATION | PASS | REVIEW | 0.62 | 14.90999984741211 EUR | NL0015001W49 |
| PUB | HOLD_OR_WATCH | PASS | ACCEPT | 0.57 | 100.9000015258789 EUR | FR0000130577 |
| RUI | HOLD_OR_WATCH | PASS | ACCEPT | 0.62 | 35.58000183105469 EUR | FR0013269123 |
| SU | NO_RECOMMENDATION | PASS | REVIEW | 0.6 | 264.3999938964844 EUR | FR0000121972 |
| SW | HOLD_OR_WATCH | PASS | ACCEPT | 0.57 | 55.04999923706055 EUR | FR0000121220 |
| THEP | NO_RECOMMENDATION | PASS | REVIEW | 0.62 | 66.9000015258789 EUR | FR0013333432 |
| VIL | HOLD_OR_WATCH | PASS | ACCEPT | 0.55 | 17.5 EUR | FR0000050049 |
| VIRI | NO_RECOMMENDATION | PASS | REVIEW | 0.57 | 89.6500015258789 EUR | FR001400PVN6 |
| WAVE | NO_RECOMMENDATION | PASS | REVIEW | 0.62 | 30.200000762939453 EUR | FR0013357621 |

**IT** - ticker: call / evidence / governance / confidence

| Ticker | Call | Ev | Gov | Conf | Price | ISIN |
|---|---|---|---|---|---|---|
| A2A | NO_RECOMMENDATION | BLOCK | ABSTAIN | 0.14 | 2.371999979019165 EUR | IT0001233417 |
| BAMI | NO_RECOMMENDATION | PASS | REVIEW | 0.48 | 14.454999923706055 EUR | IT0005218380 |
| BGN | NO_RECOMMENDATION | PASS | REVIEW | 0.48 | 62.0 EUR | IT0001031084 |
| BMED | NO_RECOMMENDATION | PASS | REVIEW | 0.48 | 23.100000381469727 EUR | IT0004776628 |
| BMPS | NO_RECOMMENDATION | PASS | REVIEW | 0.48 | 11.170000076293945 EUR | IT0005508921 |
| BPE | NO_RECOMMENDATION | PASS | REVIEW | 0.52 | 13.550000190734863 EUR | IT0000066123 |
| CPR | HOLD_OR_WATCH | PASS | ACCEPT | 0.62 | 6.420000076293945 EUR | NL0015435975 |
| ENEL | NO_RECOMMENDATION | PASS | REVIEW | 0.58 | 9.006999969482422 EUR | IT0003128367 |
| ENI | NO_RECOMMENDATION | PASS | REVIEW | 0.58 | 25.670000076293945 EUR | IT0003132476 |
| FBK | NO_RECOMMENDATION | PASS | REVIEW | 0.48 | 21.1200008392334 EUR | IT0000072170 |
| G | NO_RECOMMENDATION | PASS | ABSTAIN | 0.33 | 42.16999816894531 EUR | IT0000062072 |
| IG | NO_RECOMMENDATION | PASS | REVIEW | 0.52 | 8.437999725341797 EUR | IT0005211237 |
| ISP | NO_RECOMMENDATION | PASS | REVIEW | 0.46 | 6.195000171661377 EUR | IT0000072618 |
| MB | NO_RECOMMENDATION | BLOCK | ABSTAIN | 0.09 | 25.459999084472656 EUR | IT0000062957 |
| MONC | HOLD_OR_WATCH | PASS | ACCEPT | 0.62 | 44.20000076293945 EUR | IT0004965148 |
| PIRC | BUY_CANDIDATE | PASS | ACCEPT | 0.55 | 6.730000019073486 EUR | IT0005278236 |
| PRY | NO_RECOMMENDATION | PASS | REVIEW | 0.66 | 119.25 EUR | IT0004176001 |
| PST | NO_RECOMMENDATION | PASS | REVIEW | 0.44 | 24.350000381469727 EUR | IT0003796171 |
| RACE | NO_RECOMMENDATION | PASS | REVIEW | 0.65 | 349.75 EUR | NL0011585146 |
| REC | NO_RECOMMENDATION | BLOCK | ABSTAIN | 0.06 | 52.95000076293945 EUR | IT0003828271 |
| SPM | HOLD_OR_WATCH | PASS | ACCEPT | 0.57 | 4.711999893188477 EUR | IT0005495657 |
| SRG | HOLD_OR_WATCH | PASS | ACCEPT | 0.55 | 5.691999912261963 EUR | IT0003153415 |
| TPRO | NO_RECOMMENDATION | PASS | REVIEW | 0.41 | 31.459999084472656 EUR | IT0005482333 |
| UCG | NO_RECOMMENDATION | PASS | REVIEW | 0.46 | 77.0 EUR | IT0005239360 |
| UNI | NO_RECOMMENDATION | PASS | REVIEW | 0.39 | 25.170000076293945 EUR | IT0004810054 |

**SE** - ticker: call / evidence / governance / confidence

| Ticker | Call | Ev | Gov | Conf | Price | ISIN |
|---|---|---|---|---|---|---|
| ALFA | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 590.0 SEK | SE0000695876 |
| ASSA.B | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 349.6000061035156 SEK | SE0007100581 |
| ATCO.A | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 210.60000610351562 SEK | SE0017486889 |
| ATCO.B | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 183.1999969482422 SEK | SE0017486897 |
| AZN | HOLD_OR_WATCH | PASS | ACCEPT | 0.6 | 1576.0 SEK | GB0009895292 |
| BOL | HOLD_OR_WATCH | PASS | ACCEPT | 0.6 | 547.7999877929688 SEK | SE0020050417 |
| EPI.A | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 269.1000061035156 SEK | SE0015658109 |
| EPI.B | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 227.39999389648438 SEK | SE0015658117 |
| ERIC.A | NO_RECOMMENDATION | PASS | REVIEW | 0.54 | 96.19999694824219 SEK | SE0000108649 |
| ERIC.B | NO_RECOMMENDATION | PASS | REVIEW | 0.54 | 94.9800033569336 SEK | SE0000108656 |
| ESSITY.A | NO_RECOMMENDATION | PASS | REVIEW | 0.49 | 265.5 SEK | SE0009922156 |
| ESSITY.B | NO_RECOMMENDATION | PASS | REVIEW | 0.49 | 266.29998779296875 SEK | SE0009922164 |
| EVO | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 800.0 SEK | SE0012673267 |
| HM.B | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 167.0 SEK | SE0000106270 |
| INDU.A | NO_RECOMMENDATION | PASS | ABSTAIN | 0.34 | 510.0 SEK | SE0000190126 |
| INDU.C | NO_RECOMMENDATION | PASS | ABSTAIN | 0.34 | 508.6000061035156 SEK | SE0000107203 |
| INVE.A | NO_RECOMMENDATION | PASS | REVIEW | 0.46 | 408.0 SEK | SE0015811955 |
| INVE.B | NO_RECOMMENDATION | PASS | REVIEW | 0.46 | 416.1499938964844 SEK | SE0015811963 |
| LIFCO.B | NO_RECOMMENDATION | PASS | REVIEW | 0.6 | 319.20001220703125 SEK | SE0015949201 |
| LUG | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 658.2000122070312 SEK | CA5503711080 |
| LUMI | HOLD_OR_WATCH | PASS | ACCEPT | 0.6 | 240.6999969482422 SEK | CA5503721063 |
| SAAB.B | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 598.0999755859375 SEK | SE0021921269 |
| SAND | NO_RECOMMENDATION | PASS | REVIEW | 0.6 | 364.6000061035156 SEK | SE0000667891 |
| SKA.B | HOLD_OR_WATCH | PASS | ACCEPT | 0.55 | 267.20001220703125 SEK | SE0000113250 |
| TEL2.B | NO_RECOMMENDATION | PASS | REVIEW | 0.48 | 152.60000610351562 SEK | SE0005190238 |

**NO** - ticker: call / evidence / governance / confidence

| Ticker | Call | Ev | Gov | Conf | Price | ISIN |
|---|---|---|---|---|---|---|
| ABG | NO_RECOMMENDATION | PASS | REVIEW | 0.5 | 7.170000076293945 NOK | NO0003021909 |
| AKSO | NO_RECOMMENDATION | PASS | REVIEW | 0.58 | 39.380001068115234 NOK | NO0010716582 |
| BNOR | NO_RECOMMENDATION | PASS | REVIEW | 0.58 | 604.0 NOK | NO0010379266 |
| BONHR | HOLD_OR_WATCH | PASS | ACCEPT | 0.67 | 254.0 NOK | NO0003110603 |
| DOFG | NO_RECOMMENDATION | PASS | REVIEW | 0.56 | 135.1999969482422 NOK | NO0012851874 |
| EPR | NO_RECOMMENDATION | PASS | REVIEW | 0.63 | 84.19999694824219 NOK | NO0010735343 |
| HAUTO | BUY_CANDIDATE | PASS | ACCEPT | 0.63 | 189.6999969482422 NOK | NO0011082075 |
| IDEX | NO_RECOMMENDATION | PASS | REVIEW | 0.48 | 7.739999771118164 NOK | NO0013536078 |
| IWS | HOLD_OR_WATCH | PASS | ACCEPT | 0.63 | 61.599998474121094 NOK | NO0013461350 |
| MEDI | NO_RECOMMENDATION | PASS | REVIEW | 0.52 | 280.0 NOK | NO0010159684 |
| MORLD | HOLD_OR_WATCH | PASS | ACCEPT | 0.63 | 24.399999618530273 NOK | NO0013325506 |
| MOWI | NO_RECOMMENDATION | PASS | REVIEW | 0.51 | 206.60000610351562 NOK | NO0003054108 |
| MPCC | NO_RECOMMENDATION | PASS | REVIEW | 0.58 | 30.010000228881836 NOK | NO0010791353 |
| NORBT | NO_RECOMMENDATION | PASS | REVIEW | 0.63 | 161.89999389648438 NOK | NO0010856511 |
| ODFB | NO_RECOMMENDATION | PASS | REVIEW | 0.63 | 121.5999984741211 NOK | NO0003399917 |
| SAGA | NO_RECOMMENDATION | PASS | REVIEW | 0.43 | 1.5099999904632568 NOK | NO0010572589 |
| SMOP | HOLD_OR_WATCH | PASS | ACCEPT | 0.57 | 52.400001525878906 NOK | NO0011012502 |
| SNTIA | NO_RECOMMENDATION | PASS | REVIEW | 0.58 | 80.4000015258789 NOK | NO0013573014 |
| SOFF | NO_RECOMMENDATION | PASS | REVIEW | 0.61 | 74.5 NOK | NO0003080608 |
| SOMA | NO_RECOMMENDATION | PASS | REVIEW | 0.61 | 30.200000762939453 NOK | NO0013135368 |
| STB | NO_RECOMMENDATION | PASS | REVIEW | 0.48 | 187.3000030517578 NOK | NO0003053605 |
| WAWI | HOLD_OR_WATCH | PASS | ACCEPT | 0.58 | 179.0 NOK | NO0010571680 |
| WWI | HOLD_OR_WATCH | PASS | ACCEPT | 0.58 | 935.0 NOK | NO0010571698 |
| WWIB | HOLD_OR_WATCH | PASS | ACCEPT | 0.58 | 867.0 NOK | NO0010576010 |
| YAR | HOLD_OR_WATCH | PASS | ACCEPT | 0.6 | 402.0 NOK | NO0010208051 |

**DE** - ticker: call / evidence / governance / confidence

| Ticker | Call | Ev | Gov | Conf | Price | ISIN |
|---|---|---|---|---|---|---|
| ALV | NO_RECOMMENDATION | PASS | REVIEW | 0.5 | 429.79998779296875 EUR | DE0008404005 |
| BEI | NO_RECOMMENDATION | PASS | REVIEW | 0.5 | 81.55999755859375 EUR | DE0005200000 |
| BMW | NO_RECOMMENDATION | PASS | REVIEW | 0.61 | 55.119998931884766 EUR | DE0005190003 |
| CBK | NO_RECOMMENDATION | WARN | REVIEW | 0.27 | 38.619998931884766 EUR | DE000CBK1001 |
| DB1 | NO_RECOMMENDATION | PASS | REVIEW | 0.5 | 305.5 EUR | DE0005810055 |
| DBK | NO_RECOMMENDATION | PASS | REVIEW | 0.44 | 29.1200008392334 EUR | DE0005140008 |
| DHL | NO_RECOMMENDATION | PASS | REVIEW | 0.51 | 57.70000076293945 EUR | DE0005552004 |
| DTE | NO_RECOMMENDATION | PASS | REVIEW | 0.6 | 25.59000015258789 EUR | DE0005557508 |
| DTG | NO_RECOMMENDATION | PASS | REVIEW | 0.45 | 40.459999084472656 EUR | DE000DTR0CK8 |
| FRE | NO_RECOMMENDATION | PASS | REVIEW | 0.45 | 42.79999923706055 EUR | DE000FRE5EN2 |
| HEI | NO_RECOMMENDATION | PASS | REVIEW | 0.45 | 142.3000030517578 EUR | DE0006047004 |
| HEN | NO_RECOMMENDATION | PASS | REVIEW | 0.45 | 69.19999694824219 EUR | DE0006048408 |
| HEN3 | NO_RECOMMENDATION | PASS | REVIEW | 0.45 | 75.72000122070312 EUR | DE0006048432 |
| HNR1 | NO_RECOMMENDATION | WARN | REVIEW | 0.27 | 269.3999938964844 EUR | DE0008402215 |
| MBG | HOLD_OR_WATCH | PASS | ACCEPT | 0.59 | 39.689998626708984 EUR | DE0007100000 |
| MRK | NO_RECOMMENDATION | PASS | REVIEW | 0.45 | 137.60000610351562 EUR | DE0006599905 |
| MUV2 | NO_RECOMMENDATION | WARN | REVIEW | 0.27 | 529.4000244140625 EUR | DE0008430026 |
| RHM | NO_RECOMMENDATION | PASS | REVIEW | 0.59 | 953.4000244140625 EUR | DE0007030009 |
| RWE | NO_RECOMMENDATION | PASS | REVIEW | 0.4 | 59.2400016784668 EUR | DE0007037129 |
| SAP | NO_RECOMMENDATION | PASS | REVIEW | 0.67 | 201.25 EUR | DE0007164600 |
| SHL | NO_RECOMMENDATION | PASS | REVIEW | 0.55 | 39.91999816894531 EUR | DE000SHL1006 |
| SIE | HOLD_OR_WATCH | PASS | ACCEPT | 0.66 | 270.6499938964844 EUR | DE0007236101 |
| SRT3 | NO_RECOMMENDATION | PASS | REVIEW | 0.45 | 251.3000030517578 EUR | DE0007165631 |
| TLX | NO_RECOMMENDATION | WARN | REVIEW | 0.27 | 122.80000305175781 EUR | DE000TLX1005 |
| VOW3 | NO_RECOMMENDATION | PASS | REVIEW | 0.45 | 68.86000061035156 EUR | DE0007664039 |

<!-- APPENDIX-START -->
# Appendix - earlier report content (as of Update 5, preserved for history)

> Numbers in the summary tables of this appendix are **superseded** by the Update 7 sections above; the investigations below remain as written.

- Code validated: `d66fc6753347e4cf7c3734044a4520d5d002fa4c` (PR #52 runtime code). Branch tip `f5b6fb48d5f276a9abdab564816d351df3838abe` only adds a CI pin (`expo-doctor@1.20.4`); no runtime change.
- Test window (UTC): 2026-10-16T01:23:57.756228+00:00 .. 2026-10-16T01:48:51.640054+00:00 (DE re-run after bounded refresh: 2026-10-16T01:48:41.641401+00:00 .. 2026-10-16T01:48:51.640054+00:00)
- CI on branch (PR #52): global-backend, backend, android-bundle all PASS; android-installable-apk skipped on PRs. Validated code SHA `d66fc6753347e4cf7c3734044a4520d5d002fa4c`; report commit is the branch tip at push time.
- Mode: `BIAP_GLOBAL_ONLINE_FIRST=1`, in-process API on an isolated copy of the cached provider data; no bulk downloads, nothing written to production data.
- Sample: top companies by market cap from each exchange's deep-scan cache (25 per market, 13 each for NASDAQ/NYSE).
- Data is real cached provider data, **not live quotes**: price age is median 1.5-2.8 days (see table).

## Summary

| Mkt | Status | Tested | Analyzed | Evid P/W/B | No price | Price age med/max | Calls |
|---|---|---|---|---|---|---|---|
| US | WARN | 26 | 100% | 26/0/0 | 0 | 1.5d / 2.5d | HOLD_OR_WATCH:5, NO_RECOMMENDATION:21 |
| GB | PASS | 25 | 100% | 25/0/0 | 0 | 1.8d / 2.8d | BUY_CANDIDATE:1, HOLD_OR_WATCH:9, NO_RECOMMENDATION:15 |
| FR | PASS | 25 | 100% | 25/0/0 | 0 | 1.8d / 2.8d | HOLD_OR_WATCH:9, NO_RECOMMENDATION:16 |
| IT | WARN | 25 | 100% | 22/0/3 | 0 | 1.8d / 2.8d | BUY_CANDIDATE:1, HOLD_OR_WATCH:4, NO_RECOMMENDATION:20 |
| SE | PASS | 25 | 100% | 25/0/0 | 0 | 2.8d / 2.8d | BUY_CANDIDATE:1, HOLD_OR_WATCH:7, NO_RECOMMENDATION:17 |
| NO | WARN | 25 | 100% | 25/0/0 | 0 | 1.8d / 2.8d | BUY_CANDIDATE:10, HOLD_OR_WATCH:7, NO_RECOMMENDATION:8 |
| DE | WARN | 25 | 100% | 23/2/0 | 0 | 2.8d / 2.8d | HOLD_OR_WATCH:2, NO_RECOMMENDATION:23 |

Status rule: BLOCK = >20% of sample evidence-blocked or no coverage; WARN = any evidence-BLOCK name, non-fresh peer benchmark, BUY share >30%, missing ISIN/price; else PASS.

## Per-market detail

### USA (NASDAQ+NYSE) - WARN

- Governance: {'REVIEW': 21, 'ACCEPT': 5}; peer-scan state: {'ok': 26}; distress: {'ELEVATED_RISK': 2, 'LOW_RISK': 16, 'INSUFFICIENT_DATA': 7, 'HIGH_RISK': 1}
- Tested at: 2026-10-16T01:23:57.756228+00:00 .. 2026-10-16T01:24:18.502394+00:00
- Missing prices: none; missing ISIN: 26; degraded providers: 0
- BUY_CANDIDATE: none; fail-closed BUY (benchmark unavailable): none
- Finding: ISIN missing for 26/26

### UK (LSE) - PASS

- Governance: {'REVIEW': 15, 'ACCEPT': 10}; peer-scan state: {'ok': 25}; distress: {'LOW_RISK': 9, 'ELEVATED_RISK': 5, 'INSUFFICIENT_DATA': 8, 'HIGH_RISK': 2, 'NOT_APPLICABLE': 1}
- Tested at: 2026-10-16T01:24:19.157011+00:00 .. 2026-10-16T01:26:23.249699+00:00
- Missing prices: none; missing ISIN: 0; degraded providers: 0
- BUY_CANDIDATE: ['BHP']; fail-closed BUY (benchmark unavailable): none

### France (Euronext Paris) - PASS

- Governance: {'REVIEW': 16, 'ACCEPT': 9}; peer-scan state: {'ok': 25}; distress: {'NOT_APPLICABLE': 4, 'INSUFFICIENT_DATA': 8, 'HIGH_RISK': 6, 'LOW_RISK': 4, 'ELEVATED_RISK': 3}
- Tested at: 2026-10-16T01:26:26.888843+00:00 .. 2026-10-16T01:28:45.802477+00:00
- Missing prices: none; missing ISIN: 0; degraded providers: 0
- BUY_CANDIDATE: none; fail-closed BUY (benchmark unavailable): none

### Italy (Euronext Milan) - WARN

- Governance: {'ABSTAIN': 3, 'REVIEW': 17, 'ACCEPT': 5}; peer-scan state: {'ok': 25}; distress: {'ELEVATED_RISK': 2, 'NOT_APPLICABLE': 12, 'LOW_RISK': 4, 'INSUFFICIENT_DATA': 5, 'HIGH_RISK': 2}
- Tested at: 2026-10-16T01:28:47.557331+00:00 .. 2026-10-16T01:32:44.072118+00:00
- Missing prices: none; missing ISIN: 0; degraded providers: 0
- BUY_CANDIDATE: ['PIRC']; fail-closed BUY (benchmark unavailable): none
- Evidence BLOCK: ['A2A', 'MB', 'REC']
- Finding: 3/25 names evidence-BLOCK (fail-closed, correct)

### Sweden (Nasdaq Stockholm) - PASS

- Governance: {'ACCEPT': 8, 'REVIEW': 17}; peer-scan state: {'ok': 25}; distress: {'LOW_RISK': 14, 'ELEVATED_RISK': 2, 'INSUFFICIENT_DATA': 5, 'NOT_APPLICABLE': 4}
- Tested at: 2026-10-16T01:32:55.856270+00:00 .. 2026-10-16T01:34:56.936762+00:00
- Missing prices: none; missing ISIN: 0; degraded providers: 0
- BUY_CANDIDATE: ['SKA.B']; fail-closed BUY (benchmark unavailable): none

### Norway (Euronext Oslo) - WARN

- Governance: {'REVIEW': 8, 'ACCEPT': 17}; peer-scan state: {'ok': 25}; distress: {'NOT_APPLICABLE': 3, 'ELEVATED_RISK': 4, 'LOW_RISK': 11, 'INSUFFICIENT_DATA': 5, 'HIGH_RISK': 2}
- Tested at: 2026-10-16T01:35:00.721012+00:00 .. 2026-10-16T01:36:40.234501+00:00
- Missing prices: none; missing ISIN: 0; degraded providers: 0
- BUY_CANDIDATE: ['AKSO', 'BNOR', 'DOFG', 'EPR', 'HAUTO', 'MOWI', 'SNTIA', 'SOFF', 'SOMA', 'YAR']; fail-closed BUY (benchmark unavailable): ['MEDI']
- Finding: BUY concentration 10/25 - needs analyst review

### Germany (Xetra) - WARN

- Governance: {'REVIEW': 23, 'ACCEPT': 2}; peer-scan state: {'ok': 25}; distress: {'ELEVATED_RISK': 7, 'NOT_APPLICABLE': 6, 'INSUFFICIENT_DATA': 8, 'HIGH_RISK': 1, 'LOW_RISK': 3}
- Tested at: 2026-10-16T01:48:41.641401+00:00 .. 2026-10-16T01:48:51.640054+00:00
- Missing prices: none; missing ISIN: 0; degraded providers: 0
- BUY_CANDIDATE: none; fail-closed BUY (benchmark unavailable): none
- Finding: 2/25 names evidence-WARN

## Germany bounded refresh (approved 2026-10-16)

- Before: peer-scan cache stale for 25/25 (cachedAt 2026-10-14T08:21Z), all NO_RECOMMENDATION, no BUY possible.
- Action: one bounded `scan_global_market(DE, XETRA, deep_limit=25, time_budget_sec=480)` run, online-first, executed **only against the isolated temp data copy**. Production `/var/lib/biap-global` was not written (production `scan-cache/DE/XETRA.json` mtime still 2026-10-14 08:21Z).
- Scan result: status NO_RECOMMENDATION, rankingEligible true, 406 discovered / 403 screened (99.26%), fundamental coverage 98.77%, 405 deep-analyzed, 0 screening errors; run took 19 s. New cachedAt 2026-10-16T01:48:32Z.
- After: peer state ok 25/25; calls NO_RECOMMENDATION 23, HOLD_OR_WATCH 2; evidence PASS 23 / WARN 2 (CBK, MUV2) / BLOCK 0; no missing price/ISIN; no BUY.
- The refreshed file was subsequently promoted to production under a separate approval (see next section).

## Temporary validation copy removal

- 29,329 files, 467 MB, no hardlinks. Compared against `/var/lib/biap-global` by SHA-256: 29,327 identical, 0 missing from production, 2 differing.
- The 2 differences carry no unique content: AAPL `latest.json` differs only in `fetchedAt` (production is newer); `isin_lei.sqlite3` has identical 189,932 rows, only `meta.builtAt` differs (copy was rebuilt at validation time).
- Deleted only `/home/ubuntu/biap-validation-20261016/data`. Kept: per-ticker results `out/`, `summary.json`, `run.log`, `tools/`, code copy `src/`, and `de-refresh/` (pre-refresh DE results + fresh XETRA.json). Production data, backups, ESEF archives, DMA agents and rollback snapshots untouched. Free disk now 8.9 GB.

## Germany cache promotion (approved 2026-10-16)

- Integrity: valid JSON, schemaVersion 3, DE/XETRA, 150 deep rows, 0 rows without company; same ticker universe as previous except 7 swapped names; status NO_RECOMMENDATION, rankingEligible true.
- Provenance: produced by `scan_global_market` at code `d66fc67` from a SHA-256-verified copy of production data (online-first); sha256 `50eb260dba43...`.
- Freshness: cachedAt 2026-10-16T01:48:32Z; the peer benchmark is valid for 24 h (**expires 2026-10-17T01:48Z**, then DE fails closed again until the next refresh).
- Promotion: atomic replace of `/var/lib/biap-global/scan-cache/DE/XETRA.json` (530,485 -> 544,932 bytes). Nothing else written; no service restart.
- Rollback: previous file preserved with checksum at `/var/lib/biap-global/backup-pre-de-scan-promote-20261016T015539Z/` (ROLLBACK.txt holds the copy command).
- Verified on production API 8091 after promotion: DE/SAP sector P/E 22.39 present (benchmark restored), call NO_RECOMMENDATION.

## Italy evidence-BLOCK investigation (official sources, online)

| Name | Official finding | Verdict |
|---|---|---|
| A2A (A2A S.p.A.) | GLEIF confirms LEI 81560076E3944316DB24 = A2A S.p.A. The ESEF packages filed under that issuer in OAM 1INFO carry entity LEI 815600B7FD80E48C1896 = **A2A Energia S.p.A.** (a subsidiary). filings.xbrl.org has no entity for A2A S.p.A. | Correctly BLOCK: the parent's own ESEF is not on the public aggregator; the subsidiary's figures must not be used. Needs the parent's package from OAM 1INFO / issuer IR. |
| MB (Mediobanca) | Official FY2025 ESEF (filed 2026-04-07/15, 0 errors) covers a **6-month transition period 2025-07-01..2025-12-31**; income-statement facts use issuer extension tags; no 12-month figures. | Correctly BLOCK: never annualized (BLOCK_NO_12_MONTH_INCOME_STATEMENT). Prior FY (to 2025-06-30) net income 1,332.5M exists but is stale. No TTM derivable. |
| REC (Recordati) | Official FY2025 ESEF (0 errors) contains Revenue 2,618.4M and ProfitLoss 443.6M, but the duration contexts are **tagged 2025-12-31 -> 2026-01-01 (one day)**, a filer tagging defect. Equity is an instant and is read. | Correctly BLOCK: a 1-day "annual" period is rejected. Net income corroborates against the equity-statement column (443.6M); revenue does not. Recommend asking the issuer/OAM for a corrected package; no code change. |

No code was changed for Italy: all three blocks are source defects or a legitimate short period, and the engine fails closed on them.

## Norway BUY_CANDIDATE audit (10 names)

All ten rest on FY2025 annual figures dated 2025-12-31 (289 days old; no interim/TTM evidence for Norway), relative P/E discount to a same-sector scan median, evidence PASS (coverage 0.875-1.0, official ESEF), and decision confidence 0.56-0.67 vs accept threshold 0.55. No contradictions were recorded.

| Ticker | Sector | P/E vs sector | Peers | Distress | Conf | Flags |
|---|---|---|---|---|---|---|
| AKSO | Energy | 7.5 vs 19.5 | 12 | ELEVATED_RISK | 0.58 | elevated distress, extreme discount, near threshold |
| BNOR | Energy | 16.2 vs 19.5 | 12 | ELEVATED_RISK | 0.58 | elevated distress, near threshold |
| DOFG | Industrials | 6.9 vs 17.6 | 29 | INSUFFICIENT_DATA | 0.56 | no distress assessment, extreme discount, near threshold |
| EPR | Cons. Discr. | 17.1 vs 23.6 | 5 | LOW_RISK | 0.63 | small peer group |
| HAUTO | Industrials | 6.8 vs 17.6 | 29 | LOW_RISK | 0.63 | extreme discount, fundamental vote negative (-0.05) |
| MOWI | Cons. Staples | 12.8 vs 22.7 | 6 | INSUFFICIENT_DATA | 0.57 | no distress assessment, small peer group, near threshold |
| SNTIA | Industrials | 14.1 vs 17.6 | 29 | ELEVATED_RISK | 0.58 | elevated distress, near threshold |
| SOFF | Energy | 4.2 vs 19.5 | 12 | INSUFFICIENT_DATA | 0.61 | no distress assessment, extreme discount (likely one-off earnings) |
| SOMA | Energy | 6.3 vs 19.5 | 12 | INSUFFICIENT_DATA | 0.61 | no distress assessment, extreme discount, fundamental vote negative (-0.05) |
| YAR | Materials | 7.2 vs 23.4 | 4 | LOW_RISK | 0.67 | small peer group, extreme discount |

Assessment (counts): 3 BUYs carry ELEVATED_RISK distress; 4 have no distress assessment; 3 rest on peer groups of <=6; 6 trade at <40% of the sector P/E (typical of one-off or cyclical earnings); 2 have a non-positive fundamental vote and are carried only by the relative-P/E comparison; every one uses 289-day-old annual earnings. Only **EPR, HAUTO, YAR** carry LOW_RISK distress, and each still has one of the flags above. **None of the 10 should be presented as a clean BUY.**

**Governance rule - approved and implemented globally (commit 4a906e9, all markets via `service._analysis_payload`):** BUY_CANDIDATE is routed to REVIEW when (1) distress is not LOW_RISK (NOT_APPLICABLE is allowed; unknown/insufficient data counts as unverified), (2) the same-sector peer group has fewer than 8 valid companies, or (3) relative P/E is the only positive signal. Applying the rule to the table above, all 10 names route to REVIEW (AKSO/BNOR/SNTIA/DOFG/MOWI/SOFF/SOMA by distress, EPR/MOWI/YAR by peer count, HAUTO and SOMA by P/E-only); this is derived from the audit table, not a live re-scan. Regression coverage: `analysis/tests/test_buy_governance_rules.py`, 236 parametrised cases across every market. Interim/TTM evidence for Norway remains future work.

## USA ISIN resolution (revised 2026-10-16)

- **Superseded approach:** the earlier SEC 13(f) CUSIP -> ISO 6166 derivation is removed (commit 4a906e9). CUSIPs are CGS-licensed, and no restricted CUSIP dataset is used without confirmed licensing.
- **Current resolver (`analysis/global_markets/us_isin.py`):** legally open sources only - GLEIF (CC0) and OpenFIGI. Flag-gated, best effort, pure functions, nothing persisted. Ambiguity returns no ISIN.
- **Missing ISIN never invalidates analysis:** a US equity with no ISIN is still analysed from SEC filings and market data; the ISIN is reported as unresolved only. The earlier "25/26 resolved" figure came from the removed CUSIP chain and is no longer a claim of this report.
- Status: resolver and tests merged on the PR #52 branch; production wiring and live coverage measurement are pending deploy approval.

## Expo CI failure

- Root cause: unpinned `npx expo-doctor` resolved 1.21.4, whose schema check rejects `ios.icon` pointing at a PNG (`mobile/app.json`).
- Isolated, deploy-safe fix on PR #52: workflow pins `expo-doctor@1.20.4` (check still enforced).
- Real fix prepared in separate draft PR #54 (removes the redundant `ios.icon`): its CI runs unpinned expo-doctor and **passes** (android-bundle, typecheck). Merging it to main triggers Expo EAS build and the backend deploy workflow (`mobile/**`), so it is held for an approved deploy window.

## Remaining failures and warnings

1. **Italy**: A2A needs the parent's own ESEF from OAM 1INFO; Recordati needs a corrected package from the issuer; Mediobanca stays blocked until a 12-month statement exists.
2. **Germany**: production benchmark fresh only until 2026-10-17T01:48Z; CBK and MUV2 evidence WARN. The first controlled refresh was run 2026-10-16T02:50Z (see below). A lightweight 24 h online-first benchmark refresh is implemented (`benchmark_refresh.py`; atomic, validated, keeps one previous generation, failed refresh leaves the cache untouched and fails closed). The systemd timer units are in `deploy/systemd/` but NOT installed.
3. **Norway**: the 10 flagged BUYs now route to REVIEW under the implemented rule (live re-scan pending deploy).
4. **USA**: licence-clean resolver (GLEIF + OpenFIGI) implemented, flag-gated; live ISIN coverage not yet measured.
5. **CI/deploy**: PR #54 must wait for a deploy window; PR #52's CI relies on the doctor pin until then. Italy A2A parent ESEF and Recordati corrected filing remain unresolved; evidence BLOCK retained.
6. Sample is top-by-market-cap from cached data (prices 1-3 days old), not live quotes or the full universe.

## Decision-stability evidence

- 8 regression tests (`analysis/tests/test_global_decision_stability.py`): missing/stale/expired cache never yields BUY; fresh-to-stale never flips NO_RECOMMENDATION to BUY; contradiction preserved while fresh; legitimate discount BUY still allowed; identical evidence gives identical decisions.
- Full backend suite re-run 2026-10-16 on tip 4a906e9 (`pytest analysis/tests`, online-first flag off as in CI): **1439 passed, 0 failed**. Targeted run of governance, decision-stability, service/source-safety, decision-support, US-ISIN and benchmark-refresh tests: 279 passed.
- Test-isolation caveat (resolved, see "Controlled Germany refresh" below): with `BIAP_GLOBAL_ONLINE_FIRST=1` exported, 35 disk-persistence tests used to fail; `tests/conftest.py` now pins persistence mode per test.
- CI on 4a906e9 (PR #52): BIAP Global check and Release candidate check green. PR #54 (Expo doctor) CI green. Nothing merged, nothing deployed.
- Live example: Norway MEDI (P/E 32.1, no sector benchmark) -> REVIEW / NO_RECOMMENDATION "valuation benchmark unavailable".

## Controlled Germany refresh (2026-10-16, manual, single run)

Command: `BIAP_GLOBAL_ONLINE_FIRST=1 python -m global_markets.benchmark_refresh DE XETRA` against `/var/lib/biap-global`, 17 s, status **OK**. No timer installed, no deploy, 8091 not restarted.

| Item | Before | After |
|---|---|---|
| `scan-cache/DE/XETRA.json` cachedAt | 2026-10-16T01:48:32Z (interactive) | 2026-10-16T02:50:11Z (benchmark-refresh); 24 h expiry moves to 2026-10-17T02:50Z |
| deep rows / screening coverage / rankingEligible | 150 / 99.26% / true | 150 / 99.26% / true |
| Analysis ledger (405 analysed, evidence PASS 372 / WARN 17 / BLOCK 16, BLOCKED 11, buyQualified 0) | identical | identical |
| Calls + evidence status, 146 shared tickers | - | **0 changes**; distribution 118 NO_RECOMMENDATION/PASS, 16 /BLOCK, 12 /WARN, 4 HOLD_OR_WATCH/PASS; no BUY |
| Prices and filing periods, shared tickers | - | 0 differences (no new prices fetched; existing data only) |
| Storage | - | +575,090 bytes = new XETRA.json (+1.5 KB) and the single `.prev` rollback generation (544,932 B); no other file created or modified |

Findings to be aware of (not defects, not hidden):
- The 150-row ranked sample changed membership by 4 names: out ADS, BAS, ENR, IFX; in BMW, DTG, HEI, VOW3 (all NO_RECOMMENDATION). Scores of 12 shared names moved (e.g. SAP 0.192 -> 0.096, SIE 0.207 -> 0.241) with identical prices, i.e. the refresh re-ranks peers; calls did not change. The ranking gate count WATCHLIST_HOLD went 5 -> 4 and Top-10 swapped ENR/RHM/SAP order; ENR's own new call was not individually re-analysed.
- `batchLimit` is no longer present in the payload (interactive-scan field only).
- Rollback: `mv XETRA.json.prev XETRA.json`; pre-refresh copy also kept outside the data dir.
- Not done: a full per-company re-analysis of the 25 DE names through `/global/analyze` after the refresh. A disk-quota limit prevented building an isolated data copy; running it against the live data dir was rejected to keep historical datasets untouched.

## Persistence tests vs online-first

All 35 failures were persistence-mode tests (market/universe/fundamentals caches, history store, FX, AMF, Brreg, exchange shares, etc.) that assert files are written and inherited the ambient `BIAP_GLOBAL_ONLINE_FIRST=1`. Fix (no test disabled or weakened): `tests/conftest.py` autouse fixture `_persistence_mode_by_default` removes the flag per test; `tests/test_global_online_first.py` keeps the explicit online-first assertions (it sets the flag itself) and gains a leak test. Result: **1440 passed, 0 failed with the flag exported to 1 and with it unset.**

## Italy follow-up

- A2A, Recordati, Mediobanca: evidence BLOCK retained (no new official filing available; unchanged cause analysis above).
- Other 22 Italian names (2026-10-16 run on d66fc67, before the BUY-governance rule): 17 NO_RECOMMENDATION/PASS, 4 HOLD_OR_WATCH/PASS, 1 BUY_CANDIDATE/PASS (Pirelli, PIRC: distress LOW_RISK, but its comparison agent had no valid P/E). Under the new rule PIRC needs a verified same-sector peer group of at least 8; this was not re-run after the rule landed, so its post-rule call is **unconfirmed** and must be checked after deploy.
