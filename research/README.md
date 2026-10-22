# research/

- `paper_portfolio_<date>.json` - forward-test snapshot, frozen and read-only. Never edit; build a new dated file instead.
  `commit` / `committedAt` name the commit that added the frozen content; `contentSha256` is the hash of the file with
  `commit`, `committedAt` and `contentSha256` set to null, so the content can be verified after those fields are filled.
- `build_paper_portfolio.py` - builds a snapshot from the ledgers (read-only) and vendor closes.
- `paper_portfolio_returns.py` - BUY vs SELL vs benchmark returns from a snapshot.
- `point_in_time_feasibility_2026-10-20.md` - why a point-in-time backtest as of 2026-09-19 is not valid. Separate from the forward test.
- `daily_snapshot.py` / `run_daily_snapshot.sh` - daily point-in-time snapshot of ranks, scores, evidence status, prices, filing publication
  dates and the engine commit, one gzip per exchange plus `manifest.json`, in `/var/lib/biap-global/daily-snapshots/<UTC date>/`
  (read-only, never overwritten, ~0.35 MB/day). Cron runs it at 23:40 UTC; each exchange is a separate process under a 900 MB
  address-space limit (peak RSS measured ~50 MB). It reads the ledgers only. `filingDate` is the publication date; `filingObservedAt`
  is BIAP's retrieval date and must not be used as one. Cron points at this worktree and branch: repoint
  `run_daily_snapshot.sh`'s checkout when the branch is merged or the worktree is removed.
- `build_entry_supplement.py`, `vendor_symbols.py`, `paper_portfolio_2026-10-20_entry_supplement.json` (+ `.sha256`) - separate dated file with vendor
  closes for snapshot holdings that had no entry close (Swedish share classes ERIC.B -> ERIC-B.ST etc.), with source and retrieval time.
  The returns script uses it automatically when its `snapshotSha256` matches the snapshot. The frozen snapshot is never modified.
