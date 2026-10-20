# research/

- `paper_portfolio_<date>.json` - forward-test snapshot, frozen and read-only. Never edit; build a new dated file instead.
  `commit` / `committedAt` name the commit that added the frozen content; `contentSha256` is the hash of the file with
  `commit`, `committedAt` and `contentSha256` set to null, so the content can be verified after those fields are filled.
- `build_paper_portfolio.py` - builds a snapshot from the ledgers (read-only) and vendor closes.
- `paper_portfolio_returns.py` - BUY vs SELL vs benchmark returns from a snapshot.
- `point_in_time_feasibility_2026-10-20.md` - why a point-in-time backtest as of 2026-09-19 is not valid. Separate from the forward test.
