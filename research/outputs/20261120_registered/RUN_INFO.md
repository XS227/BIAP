# Run info
- Script: research/paper_portfolio_returns.py at commit 5f60385e5b46d251ee2180cfcdc160c3b721dbc6, sha256 83140851d05f4dbfd71ac0bc33518f0336a90f24b8eeb811f5bbb9bccdde4668, unchanged
- Inputs, taken from the same commit (identical on main): snapshot 0bd9066eb980d9293566c2cb682dce579f6d6fbf15e102eeb341e2e7e52621a1,
  entry supplement 41473deb010f0db82126d787413945111753646e666fc6ad35938516e47230c1, ISIN map 33d48abfa941ffbe6832deaa903a9e2469265a650bb25e9f96afafc4e197cabf
- Equivalent command: `python research/paper_portfolio_returns.py research/paper_portfolio_2026-10-20.json --end 2026-11-20 --json returns_2026-11-20.json`
- Run through `run_registered.py`, which calls the script's own main() and only wraps its price-fetch function to record the responses
- Prices read from Yahoo at 2026-11-27T16:37:05+00:00 (UTC), 973 symbols; kept in vendor_pull.json.gz. Later pulls can differ.
- Offline replay (reproduces returns JSON, per-holding CSV, summary and log byte for byte):
  `python3 -I run_registered.py <script> <snapshot> <new dir> --replay vendor_pull.json.gz`
- 19 Nov comparison: same command with `--end 2026-11-19` on the saved pull
- Sensitivity: `python3 -I sensitivity_posthoc.py <script> <this dir>`
- Frozen cohort files were only read. No server or production change.
