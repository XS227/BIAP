# BIAP Global — Chapter 4: Empirical Results and Statistical Protocol

> **Research manuscript · Version 2026-10-21 · PRELIMINARY DESCRIPTIVE RESULTS**
>
> **Design:** 10 countries, 12 exchange feeds, 6 primary decision agents and 4 auxiliary governance/integration components. **Freeze:** 2026-10-20. No realized 1-month performance is yet available; target assessment 2026-11-20. This is an observational *forward-test baseline*, **not** a retrospectively validated trading strategy.

## 4.1 Research design and sample

The frozen study covers the US, UK, Germany, France, Italy, Sweden, Norway, Netherlands, Finland and Spain. The US (NASDAQ and NYSE) and Germany (Xetra and Frankfurt) each contribute two venues. The engine assigned a tier or a no-recommendation status to **7,593 exchange-level universe rows**. The Section A evaluation examines **964 extreme-tier decisions**, of which **445 are BUY** and **519 are SELL**. Other decision tiers are retained in the classification census but not in this extreme-tier portfolio.

**Table 4.1 — Frozen classification census**

| Decision tier | Count | Share (%) |
|:--|--:|--:|
| BUY | 445 | 5.86 |
| ACCUMULATE | 1,040 | 13.70 |
| HOLD | 3,475 | 45.77 |
| REDUCE | 1,195 | 15.74 |
| SELL | 519 | 6.84 |
| NO RECOMMENDATION | 919 | 12.10 |
| **Total** | **7,593** | **100.00** |

Rows should not be equated automatically with unique issuers; multi-venue listings and venue-specific records must be considered when analyzing company-level counts.

## 4.2 Decision-agent framework

The six independently stored *primary* signal types are **fundamental**, **risk**, **forecast**, **comparison**, **quality**, and **liquidity**. Four supporting governance/integration functions in the broader BIAP architecture must not be misrepresented as four additional independent voting agents.

For stock $i$, let $v_{ia}^{*}\in[-1,1]$ denote the **investment-mode-adjusted** vote and $c_{ia}\in[0,1]$ its confidence for eligible agent $a$. Agents with confidence below 0.30 are omitted from the known-data score. The engine uses

$$
S_i=\frac{\sum_{a\in A_i}c_{ia}v_{ia}^{*}}{\sum_{a\in A_i}c_{ia}},\qquad
A_i=\{a:c_{ia}\geq0.30\}.
\tag{4.1}
$$

The risk vote can be recomputed from market-relative risk percentiles; the comparison vote can be recomputed using sector and cross-market peers. Therefore **stored raw agent votes do not algebraically reproduce final $S_i$**. Evidence caps, abstention, multi-agent disagreement and soft downgrade rules then affect the final tier. In investment mode, approximately the highest/lowest 10% of eligible names are candidates for BUY/SELL subject to score sign, minimum agent availability and governance constraints.

## 4.3 Cross-country decision results

**Table 4.2 — Extreme-tier decisions by country**

| Country | BUY | SELL | Mean BUY score | Mean SELL score | BUY confidence | SELL confidence | Entry priced / selected |
|:--|--:|--:|--:|--:|--:|--:|--:|
| United States | 269 | 278 | +0.395 | −0.371 | 0.628 | 0.574 | 541 / 547 |
| Germany | 54 | 80 | +0.252 | −0.406 | 0.463 | 0.435 | 133 / 134 |
| United Kingdom | 27 | 42 | +0.403 | −0.346 | 0.617 | 0.506 | 60 / 69 |
| Sweden | 25 | 37 | +0.367 | −0.398 | 0.616 | 0.553 | 60 / 62 |
| France | 23 | 26 | +0.307 | −0.441 | 0.511 | 0.480 | 47 / 49 |
| Italy | 15 | 15 | +0.364 | −0.342 | 0.521 | 0.491 | 30 / 30 |
| Norway | 12 | 12 | +0.428 | −0.482 | 0.595 | 0.554 | 23 / 24 |
| Finland | 9 | 12 | +0.388 | −0.430 | 0.557 | 0.507 | 21 / 21 |
| Netherlands | 7 | 8 | +0.422 | −0.365 | 0.556 | 0.460 | 15 / 15 |
| Spain | 4 | 9 | +0.336 | −0.429 | 0.516 | 0.473 | 11 / 13 |
| **Total** | **445** | **519** | — | — | — | — | **941 / 964** |

Country-level averages are descriptive; the selected cohort is conditional on the ranking engine and cannot establish predictive validity. Country aggregates combine exchange venues for US and DE. Differences between country sample sizes limit direct comparisons.

## 4.4 Agent-level descriptive experiment

The research team recovered **all 964 compressed per-company result blobs** from the 2026-10-20 frozen backup ledgers; each contains all six *stored raw* signal records. Means below are conditional on the final BUY/SELL cohort, and should not be interpreted as causal feature importance.

**Table 4.3 — Raw agent votes and raw confidence by final extreme tier**

| Primary agent | BUY mean vote | SELL mean vote | BUY mean confidence | SELL mean confidence |
|:--|--:|--:|--:|--:|
| Fundamental | +0.379 | −0.720 | 0.626 | 0.614 |
| Risk | −0.129 | −0.788 | 0.704 | 0.701 |
| Forecast | +0.086 | −0.106 | 0.689 | 0.688 |
| Comparison | +0.099 | −0.010 | 0.380 | 0.019 |
| Quality | +0.460 | −0.302 | 0.618 | 0.485 |
| Liquidity | +0.207 | +0.049 | 0.589 | 0.546 |

The risk signal remains negative on average even within the BUY cohort, consistent with a moderating rather than invariably bullish role. The comparison agent abstained or emitted zero-strength votes frequently; near-zero mean confidence for SELL is not evidence of predictive effectiveness. Since selection itself uses transformed signals, these descriptive differences are **mechanically selection-conditioned**.

For group $g\in\{\mathrm{BUY},\mathrm{SELL}\}$, the stored-raw-agent descriptive mean is

$$
\bar v_{a,g}=\frac{1}{n_g}\sum_{i:T_i=g}v_{ia}^{raw}.
\tag{4.2}
$$

The abstention or zero-vote rate can be reported separately as

$$
Z_{a,g}=\frac{1}{n_g}\sum_{i:T_i=g}\mathbf 1(v_{ia}^{raw}=0).
\tag{4.3}
$$

## 4.5 Evidence, price coverage and technical verification

All 445 BUY decisions have evidence **PASS**. Of 519 SELL, 516 are PASS, 2 WARN and 1 BLOCK. In total, **941/964 (97.61%)** of selected positions have a date-aligned entry price after a separately logged supplement filled 25 of the 48 originally missing values. **23** remain unpriced (3 BUY, 20 SELL); these stay in counts but are excluded from realized return calculations. Frozen snapshot SHA-256:

`0bd9066eb980d9293566c2cb682dce579f6d6fbf15e102eeb341e2e7e52621a1`

The snapshot and price-supplement checksums were revalidated on 2026-10-21. The recorded regression suite had **1,665 passing tests**, zero failures and ten warnings. Exact decision reconstruction from backup ledgers reported **964/964** tier-and-score matches. Unit test success does not prove that future stock returns will be predicted correctly.

$$
\operatorname{EntryCoverage}=\frac{N_{\mathrm{priced}}}{N_{\mathrm{selected}}}\times100
=\frac{941}{964}\times100=97.61\%.
\tag{4.4}
$$

## 4.6 Germany: diagnosed source failure and independent recovery

The 2026-10-20 price-only refresh produced `INSUFFICIENT_MARKET_COVERAGE` and `marketCoveragePct=0` for both German venues. **The archived stage-1 ledgers establish the concrete failure chain:** the public Deutsche Börse service had returned **"no downloadable daily consolidated file"**, causing the adapter to fall back to Twelve Data; **`BIAP_GLOBAL_MARKET_API_KEY` was not configured**. Thus five batch-level missing-key errors were retained and ranking eligibility was false. This is a **market-feed availability/fallback configuration fault**, not proof that all German firms lacked underlying company analyses.

On 2026-10-21 the *unchanged* Deutsche Börse 2026-10-20 daily post-trade files were fetched again and parsed in memory by the existing adapter, against the archived authoritative universes:

**Table 4.4 — Independent read-only German recheck (quotes, not reranked signals)**

| Venue | Official universe | Valid same-date post-trade matches | Coverage | Adapter errors |
|:--|--:|--:|--:|:--|
| Xetra | 409 | 406 | **99.27%** | None |
| Frankfurt | 499 | 487 | **97.60%** | None |

Xetra and Frankfurt each exceed the nominal 90% market coverage gate in this independent source-only recheck. **This does not retroactively fix the frozen October 20 scan, change 134 recorded German extreme-tier decisions, or prove that a full refreshed production scan has passed.** Recommended remediation: bounded metadata/download retries; safe date-aware fallback to a demonstrably fresh prior session when permitted; fail-closed staging until proper quote coverage is verified; rerun on an isolated research copy first; do not silently substitute absent licensed API credentials or rewrite frozen data.

## 4.7 Prospective statistical analysis (registered; outcomes pending)

Let $P_{i,0}$ denote the verified as-of-2026-10-20 entry price, and $P_{i,H}^{adj}$ the horizon-end comparable, corporate-action-consistent price when available. These outcomes **are not yet observed** at the designated one-month horizon, 2026-11-20.

$$
R_{i,H}=\frac{P_{i,H}^{adj}}{P_{i,0}^{adj}}-1.
\tag{4.5}
$$

For venue $m$ and extreme tier $g$, the equal-weighted basket (renormalized over valid priced-and-exited holdings) will be

$$
R_{m,g,H}=\frac{1}{|E_{m,g,H}|}\sum_{i\in E_{m,g,H}}R_{i,H}.
\tag{4.6}
$$

The within-venue BUY-minus-SELL predictive spread and benchmark-relative BUY excess return are planned as

$$
\Delta_{m,H}=R_{m,\mathrm{BUY},H}-R_{m,\mathrm{SELL},H},\qquad
\alpha_{m,H}=R_{m,\mathrm{BUY},H}-R_{m,\mathrm{benchmark},H}.
\tag{4.7}
$$

Cross-venue inference must specify the aggregation weights *before* observing returns. A stratified bootstrap over firms within country/venue is proposed to estimate percentile confidence limits for the cross-market spread; report attrition, nontrading names, currencies, and corporate actions. If independent effects of raw agents are to be claimed, predefine ablation experiments that **rerun the ranking without the agent**, rather than comparing conditional group means.

A preregistered noncausal market-activity diagnostic can use Spearman's rank correlation between score and same-date trading-value rank (after excluding missing activity):

$$
\rho_{S,V}=\mathrm{Corr}\big(\mathrm{rank}(S_i),\,\mathrm{rank}(\mathrm{tradingValue}_i)\big).
\tag{4.8}
$$

No $p$-values, realized returns, Sharpe ratios, abnormal performance, predictive ROC-AUC or trading-alpha claims are computed or implied by this preliminary section.

## 4.8 Limitations and research conclusion

The historical data do not provide the vintage of fundamentals, issuer membership, peer reference sets and tier rules needed for a legitimate pre-freeze point-in-time backtest; applying current models to former prices would introduce look-ahead and survivorship biases. Other caveats include concentrated US sample sizes, missing exit prices, differences in quote currency (including GBX/GBP), source outages, selection-conditioned agent statistics, corporate actions, and changing sector-relative peer pools. Germany is flagged separately until a production-equivalent end-to-end rerun is verified.

**Conclusion (decision-stage only):** BIAP Global provides an auditable ten-country, six-primary-agent forward-test baseline with 964 extreme-tier decisions, 97.61% entry-price coverage and six recoverable signal records per selected security. Any assertion of predictive skill, economic outperformance or causal agent importance remains untested.

### Reproducibility and provenance

- Frozen portfolio: `research/paper_portfolio_2026-10-20.json`; tag `paper-portfolio-2026-10-20`; snapshot commit `e2d32897e40d8a824c84d372ee91dfd0a4b67ffc`.
- Decision engine commit: `7c0606e81c5944d92566299a13692ab4c2f07dfb`.
- Full individual Section A decision ledger: [paper_portfolio_2026-10-20_sectionA.md](../evaluations/paper_portfolio_2026-10-20_sectionA.md).
- Frozen ledger backups: `/home/ubuntu/backups/paper-portfolio-ledgers-20261020` (retained on authorized research server; not new permanent bulk company-data collection).
- This paper updates **documentation only**; no frozen snapshots, historical company ledgers, DMA agents, tier decisions or production services were changed.
