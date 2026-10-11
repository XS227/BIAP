#!/bin/bash
# BIAP Global finish-job watchdog. Run by biap-finish-watchdog.timer every 20 min.
# - job alive and active      -> log, do nothing
# - job alive but stalled >40m -> kill it, resume from latest session/checkpoint
# - job gone, not complete     -> resume
# - job gone, COMPLETE marker  -> verify report/CI/prod/APK; all good -> disable timer
# Never starts a second job: watchdog itself runs under flock, resumed jobs hold job.lock,
# and any live `claude -p` BIAP job (incl. the original unlocked tmux one) blocks a resume.
#
# Env overrides (for testing): WD_DRY_RUN=1 (decide + log, never kill/start/disable),
# WD_STALL_MIN, WD_HARD_STALL_MIN, WD_NOW_OFFSET_MIN (pretend the clock is N min later).
set -uo pipefail

export HOME=/home/ubuntu
export PATH=/home/ubuntu/.local/bin:/usr/local/bin:/usr/bin:/bin

ROOT=/home/ubuntu/biap-global
REPO=$ROOT/BIAP
WD=$ROOT/watchdog
STATE=$WD/state
LOG=$ROOT/logs/biap-finish-watchdog.log
JOB_LOG=$ROOT/logs/biap-finish.log
CHECKPOINT=$ROOT/session-1011-final/CHECKPOINT.md
TASK_FILE=$ROOT/BIAP_CLAUDE_FINISH_TASK.txt
PRIORITIES=$WD/PRIORITIES.md
TRANSCRIPTS=$HOME/.claude/projects/-home-ubuntu-biap-global-BIAP
TMUX_SESSION=biap-finish
BRANCH=feat/biap-global
REPORT=docs/BIAP_GLOBAL_FINAL_REPORT_2026-10-11.md
TIMER=biap-finish-watchdog.timer
STALL_MIN=${WD_STALL_MIN:-40}
HARD_STALL_MIN=${WD_HARD_STALL_MIN:-120}   # file-idle this long = stalled even if child CPU moves
MIN_CHILD_CPU_TICKS=500                   # 5 s of child CPU between ticks = a command is really working
MAX_ATTEMPTS=8
DRY=${WD_DRY_RUN:-0}
NOW=$(( $(date +%s) + ${WD_NOW_OFFSET_MIN:-0} * 60 ))

mkdir -p "$STATE" "$(dirname "$LOG")"
log() { echo "$(date -u +%FT%TZ) [$1] ${*:2}" | tee -a "$LOG"; }

exec 9>"$WD/watchdog.lock"
if ! flock -n 9; then log INFO "another watchdog run holds the lock; skipping"; exit 0; fi

[ "$DRY" = 1 ] && log INFO "DRY RUN (no kill/start/disable)"

if [ -e "$STATE/STOPPED" ]; then log INFO "STOPPED marker present; nothing to do"; exit 0; fi

# --- find live job processes: claude in print mode working on the BIAP finish task
job_pids() {
  local p cmd
  for p in $(pgrep -x claude -u ubuntu); do
    cmd=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null) || continue
    case "$cmd" in
      *"claude -p"*"Continue BIAP Global"*|*"claude -p"*"[BIAP-WATCHDOG"*|*"claude -p --resume"*"[BIAP-WATCHDOG"*) echo "$p" ;;
    esac
  done
}

# --- newest activity (file mtimes) among transcripts, checkpoint, job log, session work dirs.
# Uses filesystem mtimes only, never timestamps written inside files (the job's own text times
# are unreliable). Mtimes in the future (clock skew) are ignored.
last_activity() {
  find "$TRANSCRIPTS" "$CHECKPOINT" "$JOB_LOG" "$ROOT/session-1011-final" "$ROOT/audit-runs" "$ROOT/wt-final" \
       -maxdepth 3 -type f -not -path '*/.git/*' -printf '%T@\n' 2>/dev/null \
    | awk -v now="$NOW" '{t=int($1); if (t <= now + 300 && t > max) max=t} END {print max+0}'
}

# --- cumulative CPU ticks of everything the job ran (live descendants + reaped children).
# Monotonic while the same job pids live; used to tell a long-running command from a hang.
descendants() { local p c; for p in "$@"; do for c in $(pgrep -P "$p"); do echo "$c"; descendants "$c"; done; done; }
job_child_cpu() {
  local total=0 p f
  for p in "$@"; do f=($(sed 's/^.*) //' /proc/$p/stat 2>/dev/null)); [ ${#f[@]} -gt 15 ] && total=$(( total + f[14] + f[15] )); done
  for p in $(descendants "$@"); do f=($(sed 's/^.*) //' /proc/$p/stat 2>/dev/null)); [ ${#f[@]} -gt 15 ] && total=$(( total + f[11] + f[12] + f[14] + f[15] )); done
  echo "$total"
}
uptime_s() { cut -d. -f1 /proc/uptime; }

# --- newest finish-job transcript (session id to resume)
latest_session() {
  local f
  for f in $(ls -t "$TRANSCRIPTS"/*.jsonl 2>/dev/null); do
    if head -c 200000 "$f" | grep -c -e 'Continue BIAP Global' -e 'BIAP-WATCHDOG' >/dev/null; then basename "$f" .jsonl; return; fi
  done
}

attempts() { [ -f "$STATE/attempts" ] && wc -l < "$STATE/attempts" || echo 0; }

start_job() {  # $1 = reason
  local reason=$1 n sid mode prompt_file last_start last_end
  n=$(attempts)
  if [ "$n" -ge "$MAX_ATTEMPTS" ]; then
    log ERROR "resume needed ($reason) but $n attempts already made (max $MAX_ATTEMPTS); giving up — needs a human. Remove $STATE/attempts to re-arm."
    return 1
  fi
  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    log INFO "tmux session $TMUX_SESSION exists without a live job; removing it before resume"
    [ "$DRY" = 1 ] || tmux kill-session -t "$TMUX_SESSION"
  fi
  sid=$(latest_session)
  # If the previous resume died within 10 min, the session itself may be broken -> fresh start.
  mode=resume
  if [ -f "$STATE/last_start" ]; then
    last_start=$(cat "$STATE/last_start"); last_end=$(last_activity)
    if [ $(( last_end - last_start )) -lt 600 ] && [ "$(cat "$STATE/last_mode" 2>/dev/null)" = resume ]; then mode=fresh; fi
  fi
  [ -z "$sid" ] && mode=fresh
  prompt_file=$STATE/prompt-$(date -u +%Y%m%dT%H%M%SZ).txt
  {
    echo "[BIAP-WATCHDOG RESUME $(date -u +%FT%TZ)] The previous run stopped ($reason)."
    echo "Resume the BIAP Global finish task from the latest checkpoint: $CHECKPOINT"
    echo "First check what is already done (git log/status in $REPO and $ROOT/wt-final, CI runs, prod /health on 127.0.0.1:8091) and do not redo or duplicate finished steps."
    echo "Priorities (MUST follow): $PRIORITIES"
    echo "Keep updating $CHECKPOINT. When everything is finished and verified, add the line 'WATCHDOG_STATUS: COMPLETE'; if blocked on the user, add 'WATCHDOG_STATUS: BLOCKED <reason>'."
    if [ "$mode" = fresh ]; then echo; echo "Original task:"; cat "$TASK_FILE"; fi
    if [ -f "$STATE/verify_failures" ]; then echo; echo "Watchdog verification failures to fix:"; cat "$STATE/verify_failures"; fi
  } > "$prompt_file"
  local resume_arg=""
  [ "$mode" = resume ] && resume_arg="--resume $sid"
  local cmd="cd $REPO && flock -n -E 75 $WD/job.lock claude -p $resume_arg \"\$(cat $prompt_file)\" --dangerously-skip-permissions 2>&1 | tee -a $JOB_LOG; rc=\${PIPESTATUS[0]}; echo \"\$(date -u +%FT%TZ) [EXIT] job exited rc=\$rc\" >> $LOG"
  log ACTION "starting job attempt $((n+1))/$MAX_ATTEMPTS mode=$mode session=${sid:-none} reason=$reason prompt=$prompt_file"
  [ "$DRY" = 1 ] && return 0
  echo "$(date -u +%FT%TZ) $mode $reason" >> "$STATE/attempts"
  echo "$NOW" > "$STATE/last_start"; echo "$mode" > "$STATE/last_mode"
  tmux new-session -d -s "$TMUX_SESSION" -c "$REPO" "bash -c '$cmd'"
  sleep 5
  if [ -n "$(job_pids)" ]; then log INFO "job started: pids $(job_pids | tr '\n' ' ')"; else log ERROR "job did not appear after start"; fi
}

verify_completion() {
  local fails=() head prod_commit
  git -C "$REPO" fetch -q origin "$BRANCH" 2>>"$LOG" || fails+=("git fetch failed")
  head=$(git -C "$REPO" rev-parse "origin/$BRANCH")
  git -C "$REPO" cat-file -e "$head:$REPORT" 2>/dev/null || fails+=("$REPORT not on origin/$BRANCH ($head)")
  # CI: every run for the branch head must be finished and not failed
  local runs; runs=$(gh run list -R "$(git -C "$REPO" remote get-url origin)" -b "$BRANCH" -c "$head" -L 50 --json name,status,conclusion,url 2>>"$LOG")
  if [ -z "$runs" ] || [ "$runs" = "[]" ]; then
    log INFO "no CI runs for $head (docs-only pushes may still trigger sync); treating as pass"
  elif echo "$runs" | jq -e 'any(.[]; .status != "completed")' >/dev/null; then
    log INFO "CI still running for $head; will re-check next tick"; return 2
  elif echo "$runs" | jq -e 'any(.[]; .conclusion != "success" and .conclusion != "skipped")' >/dev/null; then
    fails+=("CI failures on $head: $(echo "$runs" | jq -r '.[] | select(.conclusion != "success" and .conclusion != "skipped") | "\(.name)=\(.conclusion) \(.url)"' | tr '\n' ' ')")
  fi
  # Production: healthy and running the newest commit that touched deployed code
  local health; health=$(curl -s -m 10 http://127.0.0.1:8091/health)
  prod_commit=$(echo "$health" | jq -r '.commit // empty' 2>/dev/null)
  if [ "$(echo "$health" | jq -r .status 2>/dev/null)" != ok ]; then fails+=("prod /health not ok: $health")
  elif ! git -C "$REPO" merge-base --is-ancestor "$prod_commit" "$head" 2>/dev/null; then fails+=("prod commit $prod_commit not on origin/$BRANCH")
  elif ! git -C "$REPO" diff --quiet "$prod_commit" "$head" -- analysis/ deploy/ 2>/dev/null; then fails+=("prod runs $prod_commit but origin/$BRANCH $head has undeployed analysis/ or deploy/ changes")
  fi
  # APK: if mobile-global changed since the last APK build, that build must have succeeded
  local apk; apk=$(gh run list -R "$(git -C "$REPO" remote get-url origin)" -w biap-global-apk.yml -b "$BRANCH" -L 1 --json headSha,status,conclusion,url 2>>"$LOG")
  local apk_sha; apk_sha=$(echo "$apk" | jq -r '.[0].headSha // empty' 2>/dev/null)
  if [ -z "$apk_sha" ]; then
    fails+=("could not read last BIAP Global APK run (gh output: ${apk:-empty})")
  elif ! git -C "$REPO" diff --quiet "$apk_sha" "$head" -- mobile-global/ 2>/dev/null; then
    fails+=("mobile-global/ changed after last APK build $apk_sha")
  elif [ "$(echo "$apk" | jq -r '.[0].status')" != completed ]; then log INFO "APK build still running"; return 2
  elif [ "$(echo "$apk" | jq -r '.[0].conclusion')" != success ]; then fails+=("last APK build failed: $(echo "$apk" | jq -r '.[0].url')")
  fi
  log INFO "verify: head=$head prod=$prod_commit apk=$apk_sha ($(echo "$apk" | jq -r '.[0].conclusion'))"
  if [ ${#fails[@]} -eq 0 ]; then rm -f "$STATE/verify_failures"; return 0; fi
  printf '%s\n' "${fails[@]}" > "$STATE/verify_failures"
  for f in "${fails[@]}"; do log FAIL "verify: $f"; done
  return 1
}

stop_watchdog() {
  log DONE "$1 — stopping watchdog"
  [ "$DRY" = 1 ] && return 0
  date -u +%FT%TZ > "$STATE/STOPPED"
  sudo -n systemctl disable --now "$TIMER" >>"$LOG" 2>&1 && log DONE "$TIMER disabled" || log ERROR "could not disable $TIMER (STOPPED marker still makes runs no-ops)"
}

# ------------------------------------------------------------------ main
pids=$(job_pids | tr '\n' ' ')
act=$(last_activity); idle_min=$(( (NOW - ${act:-0}) / 60 )); [ "$idle_min" -lt 0 ] && idle_min=0
status_line=$(grep -E '^WATCHDOG_STATUS: (COMPLETE|BLOCKED)' "$CHECKPOINT" 2>/dev/null | tail -1)

if [ -n "$pids" ]; then
  # Stall = no file activity for >= STALL_MIN *and* no child-process CPU progress across two
  # consecutive ticks (elapsed measured with /proc/uptime, immune to wall-clock jumps), or no
  # file activity at all for >= HARD_STALL_MIN.
  cpu=$(job_child_cpu $pids); up=$(uptime_s)
  p_up= p_cpu= p_pids=; [ -f "$STATE/cpu_sample" ] && read -r p_up p_cpu p_pids < "$STATE/cpu_sample"
  [ "$DRY" = 1 ] || echo "$up $cpu $pids" > "$STATE/cpu_sample"
  if [ "$idle_min" -lt "$STALL_MIN" ]; then
    log OK "job running (pids $pids), last file activity ${idle_min}m ago, child cpu ${cpu} ticks"
    exit 0
  fi
  if [ "$idle_min" -lt "$HARD_STALL_MIN" ]; then
    if [ -z "${p_up:-}" ] || [ "${p_pids:-}" != "$(echo $pids)" ] || [ $(( up - p_up )) -gt 3600 ] || [ $(( up - p_up )) -lt 0 ]; then
      log WARN "job pids $pids: no file activity for ${idle_min}m; no valid previous CPU sample — will decide next tick"
      exit 0
    fi
    d=$(( cpu - p_cpu ))
    if [ "$d" -ge "$MIN_CHILD_CPU_TICKS" ]; then
      log OK "job pids $pids: no file activity for ${idle_min}m but child processes used ${d} CPU ticks over $(( (up - p_up) / 60 ))m — long-running command, not stalled"
      exit 0
    fi
    reason="no file activity ${idle_min}m and child cpu +${d} ticks over $(( (up - p_up) / 60 ))m"
  else
    reason="no file activity ${idle_min}m (>= hard limit ${HARD_STALL_MIN}m)"
  fi
  log WARN "job pids $pids stalled: $reason; killing and resuming"
  if [ "$DRY" != 1 ]; then
    kill -TERM $pids 2>/dev/null; sleep 30
    for p in $pids; do kill -0 "$p" 2>/dev/null && kill -KILL "$p"; done
    sleep 2; rm -f "$STATE/cpu_sample"
  fi
  start_job "stalled: $reason"
  exit 0
fi

# no job running
case "$status_line" in
  "WATCHDOG_STATUS: COMPLETE"*)
    verify_completion; rc=$?
    if [ $rc -eq 0 ]; then stop_watchdog "job COMPLETE and verified (report on GitHub, CI green, prod healthy, APK ok)"
    elif [ $rc -eq 2 ]; then log INFO "job COMPLETE; waiting on CI/APK"
    else start_job "COMPLETE claimed but watchdog verification failed"; fi ;;
  "WATCHDOG_STATUS: BLOCKED"*)
    log BLOCKED "job reports: $status_line — not resuming; needs user action"
    ;;
  *)
    start_job "job not running (last activity ${idle_min}m ago), no completion marker" ;;
esac
exit 0
