# Price refresh runner (versioned copy of what runs from /usr/local)

`biap-global-price-refresh` -> `/usr/local/bin/`, `market_driver.py` -> `/usr/local/lib/biap-global-price-refresh/`.
`market_driver.py` is byte-identical to the production copy at 2026-11-02. The runner differs from production only by P2.4:
a per-market status file (`$BIAP_GLOBAL_DATA_DIR/price-refresh-status/<EU|US>.json`) and ONE retry of a market that ended
DEADLINE / NO_PROGRESS / NO_RESULT when at least `BIAP_PRICE_REFRESH_RETRY_MIN_S` (600) seconds of budget remain.
Not installed: copying into /usr/local needs sudo and the owner's OK. Test without touching production by overriding
`BIAP_APP_DIR`, `BIAP_PY`, `BIAP_DRIVER`, `BIAP_GLOBAL_DATA_DIR`, `BIAP_PRICE_REFRESH_STATUS_DIR` (dry run 2026-11-02 with a stub
driver: Milan DEADLINE on attempt 1, DONE on attempt 2, status file ok=11 exit=0).
