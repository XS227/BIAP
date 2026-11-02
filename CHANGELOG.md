# CHANGELOG

## 2026-10-30 — production uncommitted change (documented 2026-11-02)
- `analysis/global_markets/benchmark_refresh.py` on production carries an **uncommitted** change made 2026-10-30 02:03 UTC (HEAD 6c8ada1).
- تغییر کامیت‌نشده ۳۰ اکتبر روی production، فقط فیلدهای تشخیصی برای سهم‌های ردشده؛ بدون اثر بر امتیازدهی و ورودی‌های v1.
- Adds diagnostic keys (`scannerStatus`, `releaseReasons`, `marketSource`, `marketCoveragePct`, `screenedEquities`) to the REJECTED result only. Validation, cache writes and exit codes unchanged.
- Patch: `docs/production_uncommitted_benchmark_refresh_20261030.patch`. The production file was not modified or committed.
