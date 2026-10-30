# Live deploy / rollback (BIAP Global, /home/ubuntu/biap-global/BIAP)

1. Deploy: `cd /home/ubuntu/biap-global/BIAP && git fetch --tags && git checkout <tested-tag> && sudo systemctl restart biap-global.service` (tag only commits that passed tests on a rehearsal copy).
2. Rollback: `git checkout <previous-tag> && sudo systemctl restart biap-global.service`, then check `/api/health`; restore data from the pre-deploy backup only if a re-analysis must be undone.
3. Record every move: tag the new live commit `live-YYYYMMDD` before restarting; the first pinned tag is `live-20261030` (6c8ada1).

Rule: every engine change is tested on a rehearsal copy (`deploy/rehearsal-copy.sh`) before it touches live.
The `deploy-backend` GitHub workflow is manual only (`workflow_dispatch`, `production` environment); a merge to main never deploys.

Backups: `biap-global-backup` nightly 22:50 UTC -> /home/ubuntu/backups/daily (7 daily + 4 weekly).
Liara copy is a PULL: Liara's root crontab runs `deploy/liara-pull-crontab.txt` weekly (UniWeb has no route out to Liara on port 22).
