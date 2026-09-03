# CODAL real-data validation corpus — 2026-09-04

Owner: ChatGPT session (takeover from unfinished Nasrin/Claude CODAL validation)

## Rule

A parser branch is not considered live-validated from a synthetic fixture alone. Each opinion / related-party branch must be tied to a real published issuer filing or a reliable mirror of the CODAL notice. Unknown or unavailable evidence remains `None`; no financial or audit status may be invented.

## Real cases identified

### Qualified opinion — شلرد

- Issuer/ticker: کود شیمیایی اوره لردگان / شلرد
- Period: year ended 1404/12/29
- Public reporting of the independent auditor states a **qualified opinion** and uses the expected qualified wording around an exception (`به استثنای ...`).
- Expected BIAP classification: `qualified`.
- Validation status: real external evidence identified; direct CODAL PDF should be run through `audit_parser.py` on the production relay before marking end-to-end PASS.

### Disclaimer — سفارود

- Issuer/ticker: کارخانه فارسیت دورود / سفارود
- Period: year ended 1397/12/29, audited.
- Published CODAL mirror reproduces the auditor's basis for **disclaimer of opinion** and wording that an opinion on the financial statements is not possible (`اظهارنظر ... امکانپذیر نیست`).
- Expected BIAP classification: `disclaimer`.
- Important parser finding: current `audit_parser.py` explicitly recognizes `عدم اظهارنظر` / `عدم اظهار نظر`, but real Persian auditor wording can express the same conclusion as `اظهارنظر ... امکانپذیر نیست`. This wording must be validated against the original extracted PDF text before broadening the parser; do not classify from unrelated occurrences elsewhere in a filing.

### Adverse wording — حبندر

- Issuer/ticker: حبندر
- Public CODAL mirror reports a filing referring explicitly to `اظهارنظر مردود` in an auditor review context.
- Expected branch when that exact opinion belongs to the target audit/review opinion section: `adverse`.
- Validation status: real adverse wording identified. Must confirm the original target filing and extracted opinion section before treating this as annual-financial-statement end-to-end coverage.

### Related-party / Article 129 — دیران

- Issuer/ticker: ایران دارو / دیران
- CODAL notice: `افشای معاملات موضوع ماده 129 لایحه اصلاحی قانون تجارت یا سایر اشخاص وابسته`.
- Reported tracing number: `1080345` (1402-06-14).
- This proves a real positive related-party disclosure exists for the issuer. It does **not** by itself mean `related_party_flags > 0`: BIAP's parser intentionally flags explicit risk/non-compliance language, not ordinary disclosure merely because a related-party transaction exists.

### Related-party / Article 129 — لطیف

- Issuer/ticker: محصولات کاغذی لطیف / لطیف
- Real CODAL Article-129 / related-party notices include tracing numbers `1000501`, `1002444`, and `1002308` around 1401-12-20.
- Same safety rule: ordinary compliant disclosure should classify as context with zero warnings, while explicit non-compliance / inadequate disclosure / missing approvals should produce a positive flag.

## Acceptance criteria before CODAL task is closed

1. Run the original PDFs/text through the production CODAL relay/cache, not a hand-written substitute.
2. Record tracing number, ticker, period, expected opinion/flag, parser result, and extracted evidence phrase.
3. Cover all four audit outcomes: unqualified, qualified, adverse, disclaimer.
4. Cover related-party context with both a clean `0` case and at least one genuine positive warning case. Article-129 disclosure alone is not a warning.
5. Add a regression test for every real parser defect found.
6. Never loosen matching to whole-document keyword scans; opinion classification stays bounded to the audit-opinion section and related-party warnings stay proximity-bounded.

## Current status

- Existing live PASS: فولاد -> `unqualified`, related-party flags `0` (previous production validation).
- Real external corpus for qualified/disclaimer/adverse/Article-129 identified in this takeover.
- Still open: production-relay PDF replay for the cases above and locating a filing with explicit related-party **non-compliance** wording for the positive-warning branch.

## Claude session takeover attempt (2026-09-03, ~22:30–23:25 UTC)

Owner: Claude session. Picked this up independently (before pulling and
finding the ChatGPT-session commit above) using the actual production
checkout, `/home/ubuntu/biap-kiasha/XS227-BIAP` (not `/home/ubuntu/BIAP`,
confirmed stale/separate per this file's "New external data server" section
-- that clone is missing `PyJWT` and cannot even import `api_server`).
Confirmed via `systemctl show biap-fin` that this checkout is the one
actually serving production. Synced to `main` (`27446bd` -> `2cfb7d7`, later
fast-forwarded again to `9caa89c` after pulling the commit above).

**Baseline established first, per the task's own rule (test before
changing):** `pytest tests/test_regressions.py tests/test_codal_pdf_cache.py
tests/test_codal_parser_v2.py tests/test_codal_symbol_normalization.py -q`
-> `38 passed`. Full `pytest tests/ -q` reproduces the pre-existing hang
already documented elsewhere in this project (FastAPI `TestClient`-based
files hang on first request) -- confirmed still present, not touched, not
hidden.

**A real, independent discovery method, not used by the ChatGPT-session
corpus above:** CODAL's own `/api/search/v2/q` response (reachable through
the existing `89.42.199.20:8090` relay, same `BIAP_CODAL_BASE` production
already uses -- no new proxy invented) includes a `SuperVision` object per
filing with `UnderSupervision` (0/1) and a real `Reasons` array whenever a
listed company is currently flagged. Filtering `LetterType=6` (audited
financial statements) for `UnderSupervision=1` surfaces real, currently
distressed issuers -- a much higher-probability pool for non-clean audit
opinions than picking symbols at random. 13 real candidates found this way
(`FromDate=1404/01/01` to `ToDate=1405/12/29`, first ~40 result pages):

| Symbol | Company | Tracing No | Reason (CODAL's own text) |
|---|---|---|---|
| کساوه | صنایع کاشی و سرامیک سینا | 1593551 | عدم ارائه صورت‌های مالی ۱۲ ماهه حسابرسی شدۀ شرکت اصلی و تلفیقی گروه (+2 more) |
| تیپیکو | سرمایه گذاری داروئی تامین | 1593915 | عدم ارائه صورت‌های مالی ۱۲ ماهه حسابرسی شدۀ شرکت اصلی و تلفیقی گروه (+2 more) |
| دروز | روزدارو | 1586037 | عدم ارائه صورتجلسه خلاصه مذاکرات و تکالیف مجمع |
| شبندر | پالایش نفت بندرعباس | 1563640 | عدم ارائه صورتجلسه خلاصه مذاکرات و تکالیف مجمع |
| لابسا | آبسال | 1556292 | عدم انطباق اساسنامه ناشر با نمونه مصوب سازمان |
| آبادا | تولید نیروی برق آبادان | 1549547 | عدم رعایت الزامات پذیرش (بند ۱ ماده ۳۸ دستورالعمل پذیرش) |
| **خمهر** | **مهرکام پارس** | **1553054** | **۳ سال مشمول ماده ۱۴۱ قانون تجارت** (see finding below) |
| زپارس | ملی کشت و صنعت و دامپروری پارس | 1552763 | عدم ارائه صورتهای مالی میاندوره‌ای ۶ ماهه حسابرسی شده (+1 more) |
| چکاپا | گروه صنایع کاغذ پارس | 1547626 | عدم ارائه صورتهای مالی تلفیقی میاندوره‌ای ۶ ماهه حسابرسی شده (+1 more) |
| دسینا | لابراتوارهای سینادارو | 1548507 | عدم ارائه گزارش فعالیت ماهانه مرداد ماه |
| ساروم | سیمان ارومیه | 1534834 | عدم ارائه گزارش فعالیت ماهانه مرداد ماه |
| غدام | خوراک دام پارس | 1479735 | عدم ارائه صورتهای مالی میاندوره‌ای ۶ ماهه حسابرسی شده (+1 more) |
| شیران | سرمایه گذاری صنایع شیمیائی ایران | 1520754 | عدم ارائه صورتهای مالی میاندوره‌ای ۶ ماهه حسابرسی نشده |

**خمهر (Mehrkam Pars) actually inspected -- real result, not a parser
bug:** its `۳ سال مشمول ماده ۱۴۱ قانون تجارت` (3 years under Article 141,
negative-equity) flag made it the strongest lead for a genuine non-clean
opinion, so its FY1404 audited filing (tracing_no `1553054`) was fetched end
to end through the real production path: `codal_data.latest_financial_filings`
-> real `pdf_url` -> downloaded directly (200 OK, `application/pdf`, 15305
bytes, 1 page, `Creator: Chromium`/`Producer: Skia/PDF m79`) -> `pdftotext
-layout` on the actual saved file. The extracted text is 7 bytes: the
literal word `ERROR`. This is CODAL's own PDF export failing for this
specific document (an error page rendered to PDF, not the real audited
statement) -- confirmed independently of BIAP's code by inspecting the raw
PDF bytes and running `pdftotext` by hand, not just trusting the parser.
`audit_parser.audit_opinion_from_pdf` and
`related_party.related_party_flags_from_pdf` both correctly returned `None`
for it -- this is the conservative-unknown behavior working exactly as
designed, not a bug, but this specific filing cannot serve as a validated
qualified/adverse fixture since no real classification exists to check it
against. The other 12 candidates above were not yet inspected.

**Blocked before any of the ChatGPT-session corpus's 5 candidates (شلرد,
سفارود, حبندر, دیران, لطیف) could be run through the production relay per
that section's acceptance criterion 1:** `codal-search` on the
`89.42.199.20:8090` relay started returning `HTTP 429 Too Many Requests`
partway through the discovery scan above (a ~40-page paging loop, each page
one request, run with only a 0.15s gap -- almost certainly what triggered
it). Confirmed this is a real, live condition, not a client-side artifact:
production's own `GET /stock/recommendation/46348559193224090` (فولاد, the
one symbol with an existing verified live PASS) itself degraded from its
previously-verified `codal: true` to `codal: false` /
`codalFundamentals: null` during this window -- checked directly against
`127.0.0.1:8088`, not inferred. Re-checked with spaced-out retries (8x20s,
then later 3x45s, ~23 real minutes of intermittent checking total from
first hit to last check at 23:25 UTC) -- still `429` at every check, and
production فولاد still showing `codal: false` at the final check. Given the
project's own "no forcing/no fabricating" rule applies to this session's
own process too, not just the parser: stopped retrying rather than keep
hammering a shared resource that production itself depends on. No PASS/FAIL
was recorded for any of the 5 candidates above or the 12 unexamined
`SuperVision`-flagged ones -- none were run through the real parser this
session.

**Handoff, for whoever continues (GPT session or a later Claude session):**
before resuming any CODAL work, check `curl http://89.42.199.20:8090/health`
(relay's own liveness, was `200` throughout the block) *and* a real
`codal-search` call (e.g. `GET .../codal-search/api/search/v1/companies`) --
the relay itself can report healthy while upstream CODAL is still
rate-limiting it. Confirm production's own
`GET http://127.0.0.1:8088/stock/recommendation/46348559193224090` shows
`codal: true` again as a second independent signal before resuming. Once
clear, space individual requests by several seconds and avoid unthrottled
multi-page search loops (the discovery method above is genuinely useful --
just needs a real per-request delay, e.g. 3-5s, if repeated or extended past
these 13 candidates). No code was changed this session (no parser bug was
proven against real data yet), so there is nothing to revert.
