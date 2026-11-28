#!/usr/bin/env bash
# Enable one Global agent flag in production, run checks a-g, and roll back automatically if any check fails.
# Run as ubuntu in the production tree:  deploy/enable-global-agent.sh accuracy|risk|performance|all
#   all = accuracy, then risk, then performance; stops (and rolls back only the failing step) at the first failure.
# Prerequisite: the release that contains this script is live (/health commit == HEAD of this tree), via deploy/restart-global-prod.sh.
# Rollback of one step by hand:  deploy/enable-global-agent.sh --rollback accuracy|risk|performance
# Never run during 22:45-02:00 UTC or the price-refresh windows (EU ~17:00-19:10, US ~21:15-22:15 UTC).
set -uo pipefail
cd "$(dirname "$0")/.."
ENV_FILE="${ENV_FILE:-analysis/.env.global}"
B="${BASE_URL:-http://127.0.0.1:8091}"
MAX_ROUTE_S="${MAX_ROUTE_S:-1.0}"       # risk/performance answer time limit (QA report section 8)
LOG="${LOG:-/tmp/enable-global-agent-$(date -u +%Y%m%dT%H%M%SZ).log}"
declare -A FLAG=([accuracy]=DECISION_ACCURACY_AGENT_ENABLED [risk]=RISK_AGENT_ENABLED [performance]=PERFORMANCE_AGENT_ENABLED)
declare -A KEY=([accuracy]=decisionAccuracyEnabled [risk]=riskAgentEnabled [performance]=performanceAgentEnabled)

say() { echo "[$(date -u +%H:%M:%SZ)] $*" | tee -a "$LOG"; }
restart() {
  sudo systemctl restart biap-global.service
  for _ in $(seq 1 30); do curl -fsS "$B/health" >/dev/null 2>&1 && return 0; sleep 2; done
  return 1
}
rollback() {
  local a="$1"
  say "ROLLBACK $a: removing ${FLAG[$a]} and restarting"
  sed -i "/^${FLAG[$a]}=/d" "$ENV_FILE"
  restart || say "WARN: service not healthy after rollback restart; restore the backup: cp -p $ENV_FILE.bak-* $ENV_FILE"
  local code; code=$(case $a in
    accuracy) curl -s -o /dev/null -w '%{http_code}' "$B/global/accuracy/summary?horizon=1";;
    *) curl -s -o /dev/null -w '%{http_code}' -X POST "$B/global/$a" -H 'content-type: application/json' -d '{"country":"US","exchange":"NASDAQ","ticker":"AAPL"}';;
  esac)
  [[ "$code" == 404 ]] && say "rollback $a confirmed (route answers 404)" || say "WARN: rollback $a: route answers $code, expected 404"
}

in_quiet_window() {   # refuse inside the night window and the refresh windows
  local m=$((10#$(date -u +%H) * 60 + 10#$(date -u +%M)))
  (( m >= 1365 || m < 120 )) || (( m >= 1020 && m < 1150 )) || (( m >= 1275 && m < 1335 ))
}

checks() {   # $1 = agent just enabled; prints CHECK lines, returns non-zero on the first failure
  AGENT="$1" B="$B" MAX_ROUTE_S="$MAX_ROUTE_S" SINCE="$2" python3 - <<'PY'
import json, os, subprocess, sys, time, urllib.request, urllib.error
B, agent, limit = os.environ["B"], os.environ["AGENT"], float(os.environ["MAX_ROUTE_S"])
def call(path, body=None):
    req = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="GET" if body is None else "POST")
    t = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            code, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    dt = time.monotonic() - t
    try: data = json.loads(raw)
    except ValueError: data = None
    return code, data, dt
def check(name, ok, detail=""):
    print(f"CHECK {name}: {'PASS' if ok else 'FAIL'} {detail}", flush=True)
    if not ok: sys.exit(f"check {name} failed")

st = call("/global/status")[1] or {}
keys = {"accuracy": "decisionAccuracyEnabled", "risk": "riskAgentEnabled", "performance": "performanceAgentEnabled"}
order = ["accuracy", "risk", "performance"]
on = set(order[:order.index(agent) + 1])        # earlier steps stay on, later ones must still be off
want = {keys[a]: a in on for a in order}
check("a status flags", all(st.get(k) is v for k, v in want.items()), json.dumps({k: st.get(k) for k in want}))

US = {"country": "US", "exchange": "NASDAQ", "ticker": "AAPL"}
if agent == "accuracy":
    code, d, dt = call("/global/accuracy/summary?horizon=1")
    check("b summary h=1", code == 200 and dt < 3, f"{code} {dt:.2f}s")
    p = d["pooled"]; got = (round(p["buy"]["meanReturnPct"], 2), round(p["sell"]["meanReturnPct"], 2), round(p["spreadMeanPp"], 2), len(d["markets"]))
    exp = tuple(json.loads(os.environ.get("EXPECT_ACCURACY", "[-0.35, -10.93, 10.57, 12]")))
    check("b figures", got == exp, f"got {got} expected {exp} (BUY, SELL, spread, markets)")
    code, d, _ = call("/global/accuracy/summary?horizon=3")
    check("c h=3 pending", code == 200 and "not matured" in str((d or {}).get("message", "")), str((d or {}).get("message"))[:80])
    check("d decisions", call("/global/accuracy/decisions")[0] == 200)
    check("d stock", call("/global/accuracy/stock?country=US&exchange=NASDAQ&ticker=AAPL")[0] in (200, 404))
else:
    stocks = [US, {"country": "DE", "exchange": "XETRA", "ticker": "SAP"}, {"country": "IT", "exchange": "EURONEXT_MILAN", "ticker": "ENI"},
              {"country": "KR", "exchange": "KRX", "ticker": "005930"}]
    for s in stocks:
        code, d, dt = call(f"/global/{agent}", s)
        tag = f"{s['country']}:{s['ticker']}"
        check(f"b {agent} {tag}", code == 200 and dt < limit, f"{code} {dt:.2f}s level={(d or {}).get('level')} status={(d or {}).get('status')}")
        if d.get("dataNotYetAvailable"):
            check(f"b {tag} data not yet available has no level", d.get("level") is None and "data not yet available" in " ".join(d.get("reasons") or []))
        if agent == "risk":
            check(f"b {tag} D2 response", d.get("version") == 2 and d.get("calibration") in ("preliminary", "not_calibrated", "unavailable"),
                  f"version={d.get('version')} calibration={d.get('calibration')}")
            if d.get("level") and s["country"] != "US":
                check(f"b {tag} not calibrated outside US", d.get("calibration") == "not_calibrated")
        else:
            check(f"b {tag} R7 guard live", "statementDefects" in d)
    code, _, _ = call(f"/global/{agent}", {"country": "JP", "exchange": "TSE_JP", "ticker": "5243"})
    check("c unsupported JP 5243", code == 422, str(code))
    code, _, _ = call(f"/global/{agent}", {"country": "IR", "exchange": "TSE", "ticker": "X"})
    check("e Iran excluded", code == 404, str(code))
for a in order:
    if a not in on and a != "accuracy":
        code = call(f"/global/{a}", US)[0]
        check(f"e {a} still off", code == 404, str(code))
check("f analyze unaffected", call("/global/analyze", US)[0] == 200)
j = subprocess.run(["journalctl", "-u", "biap-global", "--since", os.environ["SINCE"], "--no-pager"], capture_output=True, text=True).stdout
bad = [l for l in j.splitlines() if any(x in l.lower() for x in ("traceback", " 500 ", " 502 ", " 503 ", " 504 "))]
check("g journal clean since restart", not bad, (bad[0][:160] if bad else ""))
PY
}

enable() {
  local a="$1"
  [[ -n "${FLAG[$a]:-}" ]] || { echo "unknown agent $a" >&2; return 2; }
  if grep -q "^${FLAG[$a]}=1" "$ENV_FILE"; then say "$a already on; re-running checks only"; checks "$a" "-30min" 2>&1 | tee -a "$LOG"; return $?; fi
  cp -p "$ENV_FILE" "$ENV_FILE.bak-$(date -u +%Y%m%dT%H%M%SZ)-$a"
  sed -i "/^${FLAG[$a]}=/d" "$ENV_FILE"
  printf '\n%s=1\n' "${FLAG[$a]}" >> "$ENV_FILE"
  local since; since="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  say "ENABLE $a (${FLAG[$a]}=1), restarting"
  if ! restart; then say "FAIL: service not healthy after restart"; rollback "$a"; return 1; fi
  sleep 3
  if ! checks "$a" "$since" 2>&1 | tee -a "$LOG"; then          # pipefail: the checks' exit code decides
    say "STOP: a check failed for $a (see the FAIL line above)"; rollback "$a"; return 1
  fi
  say "$a ON, all checks passed. Watch: repeat 'journalctl -u biap-global --since -30min' in 30 minutes and tomorrow morning."
}

[[ -f "$ENV_FILE" ]] || { echo "no $ENV_FILE" >&2; exit 2; }
if [[ "${1:-}" == "--rollback" ]]; then rollback "${2:?agent}"; exit 0; fi
target="${1:?usage: $0 accuracy|risk|performance|all  (or --rollback <agent>)}"
if in_quiet_window && [[ "${FORCE_WINDOW:-0}" != 1 ]]; then echo "inside a no-restart window (UTC); try later" >&2; exit 2; fi
live="$(curl -fsS "$B/health" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("commit",""))')"
[[ "$live" == "$(git rev-parse HEAD)"* || "$(git rev-parse HEAD)" == "$live"* ]] || { echo "live commit $live is not this tree's HEAD; release first" >&2; exit 2; }
say "log: $LOG; live commit $live"
if [[ "$target" == all ]]; then
  for a in accuracy risk performance; do enable "$a" || { say "stopped at $a; earlier steps stay on (roll back with --rollback <agent>)"; exit 1; }; done
else
  enable "$target" || exit 1
fi
