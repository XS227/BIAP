# BIAP Global — Italy full live audit (2026-10-05 UTC)

Scope: Euronext Milan, official ESMA FIRDS equity universe (catalog publication 2026-09-26): **193 instruments, 193/193 audited live** via `POST /global/analyze`. Per-instrument record (storage, document id, period, LEI, normalization, reason, every attempt): `ITALY_FULL_AUDIT.json` (schema `biap-global-italy-full-audit/1`). Runner: `/home/ubuntu/italy-audit/italy_full_audit.py` (resumable, atomic checkpoint after every instrument).

## Final result (run 6 — final code, staging 127.0.0.1:8092, isolated data dir)

| Evidence status | Count |
|---|---|
| PASS | **138** |
| WARN | **32** |
| BLOCK | **23** |
| Transient failures / HTTP errors | 0 / 0 |

Official fundamental status: OFFICIAL_CURRENT 170 · OFFICIAL_STALE 13 · OFFICIAL_SOURCE_UNAVAILABLE 10.

PASS by official source: eMarket STORAGE 77 · 1INFO 46 · filings.xbrl.org ESEF 14 · issuer-hosted ESEF (ENEL path) 1.

Progression: run 1 (60 instruments, previous session) 39/10/11 → run 2 (remaining 133, pre-fix code; all 193) **130/32/31** → run 3 after fixes 137/33/23 → run 6 final **138/32/23**. No instrument moved toward BLOCK at any step.

All **32 WARN** are agent disagreement (e.g. `positive=comparison negative=fundamental`) on OFFICIAL_CURRENT FY data, not data gaps: AVIO BEC BFF BRE CE DNR FCT IRC ITW IVG LTMC MET MFEA MFEB MN NWL PLC PRO PRY RACE RAT SERI SES SGF SOL SOM TB TES TGYM TPRO TXT WBD.

## The 23 BLOCKs — every one is an upstream/official-source fact, verified

| Category | Tickers | Verified detail |
|---|---|---|
| Latest official filing is FY2024 or older (stale guard) | AEF RN TSL OPR OPS LNDR DEX CLE BST (9) | Newest storage packages: AEF eMarket 163548, RN 167846, TSL 168389, OPR 174553 (all FY2024); OPS 1INFO 160451 (FY2024); LNDR eMarket 189039 is its **FY2024** report lodged late on 2026-09-10; DEX 1INFO newest is FY2024. **CLE**: 1INFO 166984 is titled "…2025" but 1INFO's own `dataEsercizio` and the package content are FY2024 (`81560022EE962F731A95-2024-12-31`). **BST**: 1INFO row 165391 "Bilancio al 31 dicembre 2025 (ESEF)" under Banca Sistema actually contains **Neodecortech S.p.A.** (LEI 8156005E235E751B6662, taxonomy `neodecortech.it`) — rejected by the LEI gate; Banca Sistema's own FY2025 ESEF is not on either storage. |
| Official package has no inline-XBRL tags | AUTME CLI EPH GF OEC RWAY (6) | Packages exist and are LEI-attributable, but the report carries no iXBRL facts; nothing official to parse. |
| Official package embeds another entity's LEI | A2A MARR (2) | **A2A**: 1INFO FY2025 packages 166284/165545 embed `815600B7FD80E48C1896` = A2A ENERGIA S.P.A. (subsidiary). **MARR**: eMarket 180822/163889/145143 embed `815600E787F3B6565561` = LENERGIA S.P.A. **Guard not bypassed**; vendor data stays non-official. |
| Stale official + issuer not uniquely in storage register | CIR ZUC AEDES (3) | CIR: eMarket lists both "C.I.R." and "CIR" (genuinely ambiguous, refused); 1INFO "C.I.R." has no ESEF rows. ZUC: GLEIF "VINCENZO ZUCCHI - SOCIETA' PER AZIONI" vs register "ZUCCHI" — matching would require dropping a business word (deliberately forbidden). AEDES: GLEIF name does not correspond to either register entry ("AEDES S.p.A." / "Aedes SIIQ S.p.A."). |
| No official source at all | ICOP KK OROX (3) | ICOP absent from both registers; KK (Kruso Kapital) and OROX (Gens Aurea) are on the 1INFO register with no ESEF rows. |

## Systemic failures fixed this session (all with regression tests)

1. **1INFO `.xbri` packages silently dropped** (`oam_esef.Italy1InfoLocator`). 1INFO now lodges many ESEF report packages as `.xbri`; only `.zip/.xhtml/.html` were accepted. 22 of 127 cached 1INFO issuer listings contained `.xbri` rows. Now accepted (download already checks `zipfile.is_zipfile`). E.g. CE, BDB, PRO now use 1INFO FY2025 `.xbri` packages.
2. **eMarket REGEM category ignored.** Banca IFIS lodged its FY2025 ESEF (180048 IT / 180050 EN) under category 150 (REGEM), not 1.1. The eMarket locator now also reads `/xbrl/` packages from category 150 (best-effort; a REGEM outage cannot break the 1.1 listing; PDFs never; per-row landing URL records the real category). **IF: BLOCK → PASS.**
3. **Name core stripped `SA` without a word boundary**: register "SESA" became core "SE" and never matched GLEIF "SESA S.P.A.". Legal form is now stripped only as a trailing separate word, after trimming wrapping quotes (GLEIF quotes some names whole, e.g. `"INTERPUMP GROUP S.P.A."`). **SES: BLOCK → WARN (OFFICIAL_CURRENT, eMarket 187471).**
4. **GLEIF statutory alias clauses** now yield every listed name as a variant: `IN FORMA ABBREVIATA [ANCHE]`, `IN SIGLA`, `IN [VIA] BREVE`, `OVVERO`/`OV VERO`, `CON LA SIGLA`, `ABBREVIABILE IN … E IN …`, `(IN FORMA ESTESA …)`, `X SPA O Y S.P.A.`, quoted names taken whole; `SIIQ` REIT qualifier. **TRN, SL, RCS, IGD: BLOCK → PASS** (DAN also PASS).
5. **GLEIF otherNames** (former legal names) as a fallback tier, plus register `ACRONYM - LONG NAME` halves as a last tier. Each tier is consulted only if the previous one found no unique match, so no existing resolution can become ambiguous. **MTV: BLOCK → PASS** (via former name "MONDO TV S.P.A."). Also resolves MFE←Mediaset, Buzzi←Buzzi Unicem, KME←Intek, Tessellis←Tiscali.
   Register-wide regression check (`/home/ubuntu/italy-audit/compare_resolution.py`, real cached 1INFO + eMarket registers × all 192 universe LEIs): **25 resolutions gained, 0 lost.** Every new candidate still has to pass the embedded-LEI and annual-period gates.
6. **Transition-period flows mixed with prior fiscal year** (`esef._duration_value`). Annual flows were taken from the latest ~12-month period ending *on or before* period end. Mediobanca's 2025-12-31 report covers 2025-07-01..12-31 (fiscal-year change), so net income €1.33bn / OCF were FY-June-2025 values labelled FY2025-12-31 next to a Dec-2025 balance sheet. Flows are now anchored like instants (current ±7 days of period end; prior year ±10 days of period end − 365). MB now honestly reports no annual P&L/OCF for the short period (balance sheet intact).
7. **Mis-dated ESEF index entry outranked real filing** (`esef._latest_filing`). filings.xbrl.org entry 5011 is Recordati's FY2022 report indexed as **2032-12-31**; sorted by `-period_end` it hid FY2025 (24437) and produced an empty "OFFICIAL_CURRENT 2032" result. Index rows whose period ends after they were filed are now skipped. **REC: WARN (empty) → PASS, FY2025.**
8. **Fundamentals snapshot schema v3 → v4** (`cached_fundamentals`). Parser semantics changed, so v3 snapshots are no longer "fresh" (still readable as an outage fallback); production refreshes on first request instead of serving pre-fix numbers for up to 24h.

## Bank normalization — validated against live FY2025 filings

Bank (Bank of Italy Circular 262) filings tag no IFRS `Revenue` and often no plain `Equity` total. Revenue = item 120 *margine di intermediazione* only when the filing is bank-structured (fee/commission result and effective-interest revenue both tagged); equity from the issuer's own tagged totals, bounded by `EquityAndLiabilities`.

- Added: Italian label `MargineDiIntermediazione` (FinecoBank), and IFRS statement-of-changes-in-equity columns — a total-equity concept on exactly the owners column + exactly the NCI column (Banca Mediolanum `ext:TotalEquity`, Banca Profilo `ifrs-full:Equity`).
- Result (final run): revenue normalized for **all 15 banks with a 12-month FY2025 report** (ANIM AZM BAMI BDB BFF BGN BMED BMPS BPE CE FBK IF ISP PRO UCG); equity for 13 of them.
- Remaining equity gaps, deliberately not filled: **FBK** tags its FY2025 closing owners' total with an extra `PreviouslyStatedMember` restatement axis (semantically wrong tag; not accepted); **BFF** tags only the owners' total and no NCI (owners-only is not total equity).
- **MB**: no annual P&L/OCF (6-month transition period, see fix 6); equity present.

## A2A LEI guard

Unchanged and verified live in production after deploy: A2A BLOCK (OFFICIAL_SOURCE_UNAVAILABLE), blocker names both LEIs. Same guard rejects MARR (LENERGIA LEI) and BST's misattributed Neodecortech package. No official source was fabricated or relabelled.

## Tests

`pytest tests/ -k global`: **351 passed**, 2 warnings (third-party deprecations). New/extended: `test_global_italy_register_names.py`, `test_global_italy_sdir.py` (REGEM, `.xbri`), `test_global_bank_ifrs_normalization.py` (Fineco, SoCE columns, BFF guard, Mediobanca transition period), `test_global_esef_index_period_guard.py`, `test_global_evidence_pipeline.py` (schema v4).

## Deployment

`sudo -n` was available this session, so production was deployed: `sudo systemctl restart biap-global` (unit runs this working tree on 127.0.0.1:8091, data `/var/lib/biap-global`). Health OK. Post-deploy production sample of 20 (`/home/ubuntu/italy-audit/PROD_VERIFY_8091.json`): 16 PASS / 1 WARN (RACE) / 3 BLOCK (A2A, MARR, BST), matching staging on 19/20. The exception, G, is PASS on both but production served filings.xbrl.org FY2025 `24483` and staging eMarket FY2025 `180293` (same LEI, same period). The full 193-instrument audit was run on staging, not production.

## Operational notes

- Staging: 127.0.0.1:8092 is still running from the working tree with `BIAP_GLOBAL_DATA_DIR=/home/ubuntu/biap-global-staging-data` and `BIAP_GLOBAL_FUNDAMENTALS_CACHE_HOURS=0`. Stop it and delete the 6.6 GB staging data copy when no longer needed.
- `/tmp` is a 982 MB tmpfs with a per-user quota: run pytest with `--basetemp` on the home disk. The previous session's `/tmp/italy-pkgs` was moved to `/home/ubuntu/italy-audit/prev-session-italy-pkgs`.
- Nothing committed. Iran and legacy Kiasha untouched.
