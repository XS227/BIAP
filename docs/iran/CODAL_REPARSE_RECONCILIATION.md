# CODAL statement reconciliation (production DB copy, 2026-11-05)

Method: `analysis/codal_reparse.py` re-reads every stored statement's tracing number from the verified CODAL inbox, parses the
ORIGINAL filing HTML with the current parser and compares. Dry run on a copy of `listed_companies.sqlite3` (backup `pre-93`);
**production was not modified**. Per-row results: `reconcile-20261105/reconcile_rows.csv`; field-by-field before/after:
`reconcile-20261105/reconcile_fielddiff.csv`.

## Count reconciliation
| Unit | Count |
|---|---|
| stored rows that carry a CODAL statement with a tracing number | **84** (= 82 primary company rows + 2 non-primary numbered instruments `فخوز2`, `فخوز3`) |
| unique filings (tracing numbers) | **79** (5 filings are stored on 2–3 instrument rows of the same issuer) |
| rows: verified / corrected / unverified | **36 / 20 / 28** (= 84) |
| unique filings: verified / corrected / unverified | 32 / 19 / 28 (3 filings are `verified` on the primary row and `corrected` on a numbered-instrument row) |
| primary rows whose balance sheet balances (±1%) before → after | 43 → 58 of 82 |

The earlier "39 of 82" counted *primary rows that failed the balance identity or lacked inputs* on the stored data (before any re-read);
"36 + 13 + 35 = 84" counted *all rows with a tracing number* by re-verification outcome. They are different populations, which is why
they do not match one-to-one. After the parser fix below the outcome is 36 + 20 + 28.

## Root causes found
1. **Old-parser rows** took a wrong balance-sheet row (e.g. «جمع دارایی‌های غیرجاری» instead of «جمع دارایی‌ها» for سپیدار) or the wrong
   column (سپرمی revenue shifted one period; چکاپا equity shifted). 9 rows (8 filings) had wrong totals.
2. **Numbered instruments** (`فخوز2/3`) kept stale copies of the issuer's statement with different (wrong) totals.
3. **Parser failed closed on side-by-side balance sheets** (assets left, equity+liabilities right, six numbers in one row):
   7 statements (تامین مسکن, رکارت, سپرمی, مشاور ایده, واعتضاد, وزرین, وسپهر الوند) were unparseable. Fixed by reading only
   the numbers that follow the row's own label (stop at the next text cell). Five plain numbers still fail closed.
4. **28 statements have no original filing in the inbox** → `unverified` (not corrected, not deleted). They were added to the
   existing fetcher's `priority.txt` (rate-limited pipeline; no direct CODAL calls).
5. **5 statements are for long-past periods** (1396–1402, e.g. سپرمی 1396/08/30) – flagged `stale` and excluded from peer statistics.

## Independent checks on the 56 originals available
- Units: every filing states «به میلیون ریال» (56/56).
- Reporting scope: stored scope equals the title's scope for 56/56.
- Period end in the filing header equals the date in the stored title for 56/56.
- Balance identity (assets = liabilities + equity): tolerance 1%; all genuinely balanced stored rows are within 0.1% except one (حآسا3, 1.8%, `unverified`).
- Field changes: 321 (278 fill a previously missing field, 43 replace a value, 0 clear a value the parser rejects). Core replacements: total assets/liabilities on 9 rows (8 filings), equity on 1, revenue on 1.
