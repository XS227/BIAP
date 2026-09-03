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
one request, run with only a 0.15s gap -- suspected at the time as the
trigger). Confirmed this is a real, live condition, not a client-side
artifact: production's own `GET /stock/recommendation/46348559193224090`
(فولاد, the one symbol with an existing verified live PASS) itself degraded
from its previously-verified `codal: true` to `codal: false` /
`codalFundamentals: null` during this window -- checked directly against
`127.0.0.1:8088`, not inferred.

**Root-caused via SSH to the relay host itself (2026-09-03, ~23:30-23:55
UTC), correcting the "this session caused it" assumption above:** read
`/root/BIAP/analysis/relay_server.py` (no rate-limiting/backoff logic of its
own -- it's a bare proxy) and `/etc/nginx/sites-available/biap-codal-gateway`
(no `limit_req`, just an IP allowlist + `proxy_pass`), then
`/root/BIAP/analysis/relay.log` (150,150 lines, uvicorn access log, covers
the relay's full uptime since it started 2026-08-26). The `429` responses
carry `Server: nginx/1.24.0 (Ubuntu)` -- CODAL's own server signature, not
the relay's -- confirming the 429 is genuinely coming from upstream CODAL,
not anything the relay or this host's nginx imposes. Critically: **the
first `codal-search` 429 in the log is at line 1029 of 150,150** -- i.e.
essentially from very early in the relay's multi-day production life, long
before this session existed. Of the last 300 `codal-search` log lines
checked at the time, 44 were `429` and only 2 were `200` (~4% success). This
is a **chronic, high-failure-rate condition on CODAL's `search.codal.ir`
specifically** (`tsetmc-cdn`, `codal-excel` and `tsetmc-old` in the same log
are essentially all `200 OK` throughout -- only the search endpoint is
affected), not something this session's scan freshly triggered, and not a
fixed-duration block that will simply "clear" -- it is probabilistic, with
a real but small chance of success on any given request. This explains why
every earlier session's "still need a real non-clean example" gap was never
closed: not for lack of trying, but because the access channel itself has
been failing most of the time all along, until now nobody had traced it to
the relay's own logs to see this shape.

Given that corrected picture, retried with modest backoff (5 attempts per
symbol, 6s apart, `search/v2/q` with `Symbol=`, the shape that showed
occasional `200`s in the tail of the log) against all 5 of the ChatGPT
corpus's candidates -- **0/25 succeeded in this window** (all `429`).
Re-checked with spaced-out retries before and after that batch (8x20s, then
3x45s, then the 6x8s/5x6s batches above -- roughly 40 real minutes of
intermittent, deliberately non-abusive checking total, well under the
volume production itself generates) -- still failing at the last check.
Stopped rather than push further: the success rate right now appears to be
near 0%, and continuing to add load to a chronically-struggling shared
upstream endpoint is not proportionate to the marginal chance of a hit. No
PASS/FAIL was recorded for any of the 5 candidates above or the 12
unexamined `SuperVision`-flagged ones -- none were run through the real
parser this session.

**Recommended follow-up, separate from the CODAL-validation task itself:**
this chronic `search.codal.ir` failure rate for the relay's outbound IP
(`89.42.199.20`) looks like a real, standing infrastructure problem worth
its own investigation/ask (e.g. whether that IP is specifically
rate-limited by CODAL, whether request volume from `biap-fin` itself needs
throttling, or whether a different source IP/access pattern would fare
better) -- flagged in `TASKS.md` rather than attempted here, since fixing it
is infrastructure work, not audit-parser validation.

**Handoff, for whoever continues (GPT session or a later Claude session):**
this is not a "wait for it to clear" condition -- treat every `codal-search`
call as having a real but low (roughly single-digit-percent, observed 2/46
in one sample, 0/25 in another) chance of success at any given moment, not a
binary up/down state. `curl http://89.42.199.20:8090/health` being `200`
proves only the relay process is alive, not that `codal-search` will
succeed -- always test with a real `codal-search` call (e.g.
`GET .../codal-search/api/search/v1/companies`) before trusting an empty
result from `codal_data.py` as "no data" rather than "rate-limited this
try." A retry loop (~5 attempts, several seconds apart, on the specific
`search/v2/q?Symbol=...` call needed) is the right pattern, same as used
above -- not a long wait-then-single-retry. Once a candidate's filing list
comes back, immediately cache/save the result (e.g. to a local JSON, as
`codal_flagged.json`/`candidate_filings.json` were this session) so a
later PDF-fetch/parse step doesn't need to re-win the same low-probability
draw. Avoid unthrottled multi-page search loops for new discovery scans
specifically (the discovery method above is genuinely useful --
just needs a real per-request delay, e.g. 3-5s, if repeated or extended past
these 13 candidates). No code was changed this session (no parser bug was
proven against real data yet), so there is nothing to revert.
