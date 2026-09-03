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
