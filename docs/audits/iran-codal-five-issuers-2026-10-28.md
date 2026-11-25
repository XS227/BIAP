# BIAP Iran — CODAL five-issuer read-only extraction check (2026-10-28)

**Status:** five targeted CODAL HTML exports parsed by the revised Iran-only parser. Both balance-sheet periods passed the algebraic identity check for every sample. **Not** a fresh Kiasha recommendation or external audit.

Source: original CODAL financial-statement exports through the configured CODAL relay. Figures are **in each source export's reported unit**, without currency conversion. Historical Kiasha actions and existing databases have not been changed.

| Symbol | Report tracing no. | Revenue | Net profit | Total assets | Liabilities | Equity | Balance |
|---|---|---:|---:|---:|---:|---:|---|
| سپیدار | 1531915 | 12,085,377 | 8,166,298 | 27,962,957 | 3,136,271 | 24,826,686 | PASS |
| مبین | 1558868 | 801,264,354 | 131,533,844 | 1,009,985,861 | 808,522,157 | 201,463,704 | PASS |
| فخوز | 1584708 | 1,290,153,813 | 87,943,568 | 1,462,046,402 | 1,002,795,175 | 459,251,227 | PASS |
| دلقما | 1524946 | 23,467,868 | 6,373,576 | 32,946,982 | 15,994,754 | 16,952,228 | PASS |
| چکاپا | 1504023 | 15,682,837 | -609,980 | 25,057,957 | 14,524,034 | 10,533,923 | PASS |

## Sources (exact filing exports used)
- سپیدار: https://excel.codal.ir/service/Excel/GetAll/jQQQaQQQ13mEO7vjhQhoQS5Kv8vQ%3d%3d/0
- مبین: https://excel.codal.ir/service/Excel/GetAll/tJpxQi0biH0na5Mo1XHmOA%3d%3d/0
- فخوز: https://excel.codal.ir/service/Excel/GetAll/ig1fMrU6L91kOOObOOOYe6RZLQQQaQQQXg%3d%3d/0
- دلقما: https://excel.codal.ir/service/Excel/GetAll/NZkXA8eyMOGF1CsQQQaQQQ0axHHw%3d%3d/0
- چکاپا: https://excel.codal.ir/service/Excel/GetAll/zOrWFaNEieOOObOOOXQQQaQQQzRShS9Wqg%3d%3d/0

## Reliability scope
- Identity: Assets = liabilities + equity, checked for current and comparative periods; tolerance 1% of assets.
- Extractor fix: match complete total labels instead of prefix matches (which matched non-current/current subtotals); select current/comparative columns rather than two largest numbers.
- Provenance and balance are required by Iran Kiasha evidence guard. Without them, potential BUY/SELL becomes HOLD; numeric score remains descriptive.
- An identity PASS is only an initial arithmetic control. It does not independently authenticate auditor opinion, compare interim vs audited revisions, or verify every financial metric.
- The existing stored CODAL rows still contain bad pre-fix balances until an explicitly reviewed re-ingestion is performed. The historical portfolio and decisions are immutable in this change.
- No production release, APK publication, or Global engine change is implied by this audit.
