# Live deploy / rollback (BIAP Global, /home/ubuntu/biap-global/BIAP)

1. Deploy: `cd /home/ubuntu/biap-global/BIAP && git fetch --tags && git checkout <tested-tag> && sudo systemctl restart biap-global.service` (tag only commits that passed tests on a rehearsal copy).
2. Rollback: `git checkout <previous-tag> && sudo systemctl restart biap-global.service`, then check `/api/health`; restore data from the pre-deploy backup only if a re-analysis must be undone.
3. Record every move: tag the new live commit `live-YYYYMMDD` before restarting; the first pinned tag is `live-20261030` (6c8ada1).

Rule: every engine change is tested on a rehearsal copy (separate worktree + copied ledgers) before it touches live.
The `deploy-backend` GitHub workflow is manual only (`workflow_dispatch`, `production` environment); a merge to main never deploys.
