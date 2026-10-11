# BIAP Global finish-job watchdog

Server-side watchdog for the autonomous BIAP Global "finish" job (a non-interactive
`claude -p` run in tmux session `biap-finish` on the VPS). It keeps the job going across
SSH disconnects, crashes, stalls and reboots, and switches itself off once the job's
results have been verified independently.

Installed and enabled 2026-10-11 11:43Z.

## Where things live

| What | Path |
|---|---|
| Live script and units (what systemd runs) | `/home/ubuntu/biap-global/watchdog/` |
| Repo copy (this directory) | `tools/biap-finish-watchdog/` |
| Installed units | `/etc/systemd/system/biap-finish-watchdog.{service,timer}` |
| Watchdog log | `/home/ubuntu/biap-global/logs/biap-finish-watchdog.log` (also `journalctl -u biap-finish-watchdog`) |
| Job output | `/home/ubuntu/biap-global/logs/biap-finish.log` |
| Job checkpoint | `/home/ubuntu/biap-global/session-1011-final/CHECKPOINT.md` |
| Original task prompt | `/home/ubuntu/biap-global/BIAP_CLAUDE_FINISH_TASK.txt` |
| Market priority order | `/home/ubuntu/biap-global/watchdog/PRIORITIES.md` (DE → IT → Nordic → UK/US → rest) |
| State (attempt count, resume prompts, STOPPED marker) | `/home/ubuntu/biap-global/watchdog/state/` |
| Job transcripts (session ids for `--resume`) | `~/.claude/projects/-home-ubuntu-biap-global-BIAP/*.jsonl` |

The live copy is kept outside the git checkout on purpose, so branch switches, rebases or
worktree changes made by the job can never change what systemd runs. If you change the
script, edit the live copy, run `install-and-test.sh`, then copy it back here.

## Schedule and persistence

- `biap-finish-watchdog.timer` is a **system** unit (`WantedBy=timers.target`, enabled). It runs
  5 min after boot and then every 20 min (`OnUnitActiveSec=20min`, `Persistent=true`).
- It does not depend on a login session, so SSH disconnects don't affect it. logind has
  `KillUserProcesses=no`. The original job's SSH session (1129) is already in state `closing`
  and the job is still running.
- After a reboot the tmux job is gone. The first tick (boot + 5 min) sees no job and resumes it.
  Tested: a tmux server started from this oneshot unit (`KillMode=process`) keeps running
  after the unit goes inactive.

## What each tick does

1. Takes `watchdog.lock` with `flock -n`. If another tick is running, it exits.
2. Looks for a live job: a `claude` process whose command line is the finish task or a
   `[BIAP-WATCHDOG` resume prompt.
3. Activity is the newest mtime among the job transcripts, CHECKPOINT.md, the job log,
   `session-1011-final/`, `audit-runs/` and `wt-final/`.
   - Job alive and active within the last 40 min: logs `OK` and does nothing else.
   - Job alive but idle for 40 min or more: sends TERM, then KILL after 30 s, then resumes.
   - No job and no completion marker: resumes.
4. Resume runs `claude -p --resume <latest finish-job session> "<resume prompt>"` in tmux session
   `biap-finish`, wrapped in `flock -n $WD/job.lock`. A second job cannot start even if two
   watchdogs raced. If the previous resume died within 10 min, the watchdog starts fresh with
   the original task instead. The resume prompt points the job at CHECKPOINT.md and
   PRIORITIES.md and tells it not to redo finished steps. There are at most 8 resume attempts;
   after that it logs `ERROR ... needs a human`.
5. Completion: the job appends `WATCHDOG_STATUS: COMPLETE` (or `WATCHDOG_STATUS: BLOCKED <reason>`)
   to CHECKPOINT.md. On COMPLETE the watchdog runs its own checks and does not take the job's word:
   - `docs/BIAP_GLOBAL_FINAL_REPORT_2026-10-11.md` exists on `origin/feat/biap-global`
   - every CI run on the branch head has completed with success or skipped
   - prod `127.0.0.1:8091/health` reports `status: ok`, and its commit has no undeployed
     `analysis/` or `deploy/` changes compared with the head
   - the latest `biap-global-apk.yml` run succeeded and nothing in `mobile-global/` changed after it

   If all of these pass, it writes `state/STOPPED` and runs `systemctl disable --now` on the timer.
   If any fail, it resumes the job with the failures listed. While CI or the APK build is still
   running, it waits for the next tick. On BLOCKED it logs and stops resuming.

## Operating it

```bash
systemctl list-timers biap-finish-watchdog.timer      # next/last run
systemctl status biap-finish-watchdog.service         # last result
tail -f ~/biap-global/logs/biap-finish-watchdog.log   # decisions
tmux attach -t biap-finish                            # watch the job (detach: Ctrl-b d)

touch ~/biap-global/watchdog/state/STOPPED            # pause (every tick becomes a no-op)
rm ~/biap-global/watchdog/state/STOPPED               # unpause
rm ~/biap-global/watchdog/state/attempts              # re-arm after hitting 8 attempts
sudo systemctl start biap-finish-watchdog.service     # run one tick now
sudo systemctl disable --now biap-finish-watchdog.timer   # remove permanently

# test without side effects (decide and log only; never kill/start/disable)
WD_DRY_RUN=1 bash ~/biap-global/watchdog/biap-finish-watchdog.sh
WD_DRY_RUN=1 WD_NOW_OFFSET_MIN=60 bash ~/biap-global/watchdog/biap-finish-watchdog.sh   # simulate a stall

bash ~/biap-global/watchdog/install-and-test.sh       # (re)install units and run tests 1-4
```

## Notes for future Claude sessions

- Do **not** start another `claude -p` finish job by hand while the watchdog is enabled. Check
  `pgrep -af "claude -p"` and the watchdog log first.
- Do not run `tmux kill-server`. It also kills the job.
- The job may run with `--dangerously-skip-permissions`. It was told: no data deletion, no reboot,
  no changes to unrelated projects, and don't stop production services.
- Pushes to `feat/biap-global` that touch `analysis/global_markets/**` (and the other paths in
  `setup-biap-global-server.yml`) are production deploys.
