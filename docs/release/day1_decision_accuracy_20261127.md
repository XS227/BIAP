# Day 1: enable the Decision Accuracy agent in production (prepared 2026-11-27, NOT done)

Scope: one flag, `DECISION_ACCURACY_AGENT_ENABLED`, in `/home/ubuntu/biap-global/BIAP/analysis/.env.global` (read by `biap-global.service` through `EnvironmentFile`). Risk and Performance stay off. The agent is read-only: it serves versioned cohort files from the repository (`analysis/global_markets/data/decision_accuracy`), runs no enrichment and makes no outbound call, so it adds no per-request cost and the numbers do not depend on production price data. Iranian listings are dropped from its output.

## State verified on 2026-11-27 (before any change)
- `/health` reports commit `94cd361`; `/global/status`: `decisionAccuracyEnabled: false`, `riskAgentEnabled: false`, `performanceAgentEnabled: false`.
- `GET /global/accuracy/summary?horizon=1` answers 404 (flag off). `.env.global` has no `*_AGENT_ENABLED` line, is owned by `ubuntu`, mode 600.
- Same code on the staging copy (127.0.0.1, flag on): HTTP 200, 1.4 s, 12 markets, venue-equal BUY -0.354%, SELL -10.929%, spread 10.575 pp, 95% interval 7.64 to 13.42 (the numbers to expect).

## When
Outside 22:45-02:00 UTC and outside the price-refresh windows (EU about 17:00-19:10, US about 21:15-22:15 UTC). The restart drops requests in flight for a few seconds (one worker).

## Steps (run as `ubuntu`)
```
cd /home/ubuntu/biap-global/BIAP/analysis
# 1. back up the env file
cp -p .env.global .env.global.bak-$(date -u +%Y%m%d)
# 2. add the flag (the leading newline protects against a file without a final newline)
printf '\nDECISION_ACCURACY_AGENT_ENABLED=1\n' >> .env.global
# 3. restart (the one sudo rule available to ubuntu)
sudo systemctl restart biap-global.service
# 4. wait until healthy (max 60 s); must print the release commit 94cd361...
for i in $(seq 1 30); do curl -fsS http://127.0.0.1:8091/health && break; sleep 2; done
```

## Checks (all against 127.0.0.1:8091)
```
B=http://127.0.0.1:8091
# a) only this flag changed
curl -s $B/global/status | python3 -c 'import sys,json;d=json.load(sys.stdin);print({k:v for k,v in d.items() if "gent" in k or "ccuracy" in k})'
#    expect decisionAccuracyEnabled True, riskAgentEnabled False, performanceAgentEnabled False
# b) 1-month result
curl -s -w ' [%{http_code} %{time_total}s]\n' "$B/global/accuracy/summary?horizon=1" | tail -c 80
#    expect 200 in under 3 s; then the figures: venue-equal BUY -0.35%, SELL -10.93%, spread 10.57 pp (7.6 to 13.4), 12 markets
curl -s "$B/global/accuracy/summary?horizon=1" | python3 -c 'import sys,json;d=json.load(sys.stdin);p=d["pooled"];print(p["weighting"][:12],round(p["buy"]["meanReturnPct"],2),round(p["sell"]["meanReturnPct"],2),round(p["spreadMeanPp"],2),len(d["markets"]))'
# c) longer horizons are pending, nothing extrapolated
curl -s "$B/global/accuracy/summary?horizon=3" | python3 -c 'import sys,json;print(json.load(sys.stdin)["message"])'     # 3-month horizon not matured: due 2027-01-20
# d) per-decision list and one stock
curl -s -o /dev/null -w "%{http_code}\n" "$B/global/accuracy/decisions"
curl -s -o /dev/null -w "%{http_code}\n" "$B/global/accuracy/stock?country=US&exchange=NASDAQ&ticker=AAPL"     # 200, or 404 if that stock has no record
# e) Iran stays out; Risk and Performance still off
curl -s -o /dev/null -w "%{http_code}\n" -X POST $B/global/risk -H 'content-type: application/json' -d '{"country":"US","exchange":"NASDAQ","ticker":"AAPL"}'          # 404
curl -s -o /dev/null -w "%{http_code}\n" -X POST $B/global/performance -H 'content-type: application/json' -d '{"country":"US","exchange":"NASDAQ","ticker":"AAPL"}'   # 404
# f) the rest of Global is unaffected
curl -s -o /dev/null -w "%{http_code}\n" -X POST $B/global/analyze -H 'content-type: application/json' -d '{"country":"US","exchange":"NASDAQ","ticker":"AAPL"}'      # 200
# g) journal: no traceback, no 5xx, over the 30 minutes after the restart
journalctl -u biap-global --since "-30min" --no-pager | grep -ciE "traceback|error| 5[0-9][0-9] " 
```
The app shows the Track record card and the More item only in a build that contains the track-record screens; builds without them are unaffected. Horizons 3, 6 and 12 months show "pending" until 2027-01-20, 2027-04-20 and 2027-10-20.

Watch: repeat (g) after 30 minutes and the next morning. Expect no tracebacks and no change in memory (`systemctl status biap-global` Memory) beyond normal.

## Rollback (under one minute, no data change)
```
cd /home/ubuntu/biap-global/BIAP/analysis
sed -i '/^DECISION_ACCURACY_AGENT_ENABLED=/d' .env.global      # or: cp -p .env.global.bak-<date> .env.global
sudo systemctl restart biap-global.service
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8091/global/accuracy/summary?horizon=1"     # 404 again
```
The app hides the section by itself (it reads the flag from `/global/status`). If the code release itself must be undone: `git checkout 96fa9d3` in the production tree and `sudo deploy/restart-global-prod.sh 96fa9d3`.

## Not part of Day 1
Risk agent (Day 2, after D2 is released and its distribution is confirmed) and Performance agent (Day 3). Each needs its own approval.
