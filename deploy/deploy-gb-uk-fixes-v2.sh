#!/usr/bin/env bash
# Deploy GB/UK evidence fixes (commit 5ee61bc; same patch as 3065e75 on fix/gb-uk-audit-fixes-20261022) to production.
# Run manually, only after explicit approval. Not between 23:35-23:50 UTC (snapshot) or around 01:00 UTC.
# Safety: preflight + isolated tests + backups BEFORE touching prod; aborts on any failure; rollback never uses reset --hard.
set -euo pipefail
PROD=/home/ubuntu/biap-global/BIAP
COMMIT=5ee61bc
LEDGER=/var/lib/biap-global/analysis-ledger/GB__LSE.sqlite3
EXPECT_HEAD=7362aa7ca4a626d623cf07f2f9e22e10a58dcb97
B=/home/ubuntu/backups/gb-uk-fixes-deploy-$(date -u +%Y%m%dT%H%M%SZ)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
cd "$PROD"

echo "== preflight"
[ "$(git rev-parse HEAD)" = "$EXPECT_HEAD" ] || { echo "ABORT: prod HEAD moved ($(git rev-parse --short HEAD) != ${EXPECT_HEAD:0:7})"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "ABORT: tracked changes in prod tree"; git status --short; exit 1; }
git cat-file -e "$COMMIT^{commit}"
git diff "$COMMIT~1" "$COMMIT" -- analysis/global_markets/esef.py analysis/global_markets/oam_esef.py analysis/global_markets/service.py > "$T/fix.patch"
git apply --check "$T/fix.patch"
avail_mb=$(df -Pm /home/ubuntu/backups | awk 'NR==2{print $4}'); [ "$avail_mb" -ge 2048 ] || { echo "ABORT: <2GB free"; exit 1; }

echo "== isolated tests (prod untouched)"
mkdir -p "$T/copy" "$T/data"
git archive HEAD analysis | tar -x -C "$T/copy"
( cd "$T/copy" && git init -q . && git apply "$T/fix.patch" )
git show "$COMMIT:analysis/tests/test_global_uk_audit_fixes.py" > "$T/copy/analysis/tests/test_global_uk_audit_fixes.py"
( cd "$T/copy/analysis" && BIAP_GLOBAL_DATA_DIR="$T/data" PYTHONPATH=. "$PROD/analysis/.venv-global/bin/python" -m pytest tests/test_global_uk_audit_fixes.py tests/test_global_uk_nsm.py -q -p no:cacheprovider )

echo "== backups"
mkdir -p "$B/files/analysis/global_markets"
git rev-parse HEAD > "$B/prod-HEAD-before.txt"
for f in esef oam_esef service; do cp -p analysis/global_markets/$f.py "$B/files/analysis/global_markets/"; done
python3 - "$LEDGER" "$B/GB__LSE.sqlite3" <<'PY'
import sqlite3,sys
s=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); d=sqlite3.connect(sys.argv[2]); s.backup(d)
assert d.execute('pragma integrity_check').fetchone()[0]=='ok'; print('ledger backup ok')
PY
echo "backup dir: $B"

echo "== apply (cherry-pick $COMMIT)"
git cherry-pick "$COMMIT"
git log --oneline -2

cat > "$B/rollback.sh" <<RB
#!/usr/bin/env bash
# Rollback without reset --hard: revert only the deploy commit (history preserved), restart.
set -euo pipefail
cd $PROD
git revert --no-edit HEAD
sudo systemctl restart biap-global.service
RB
chmod +x "$B/rollback.sh"
echo "== restart + health"
sudo systemctl restart biap-global.service
sleep 8
code=$(curl -s -m 15 -o /dev/null -w "%{http_code}" http://127.0.0.1:8091/docs)
echo "api /docs: $code"
[ "$code" = 200 ] || { echo "UNHEALTHY -> rollback:"; echo "  bash $B/rollback.sh"; exit 1; }

echo "Deployed. Rollback: bash $B/rollback.sh   (ledger copy: $B/GB__LSE.sqlite3 — restore only if the ledger refresh is later judged bad)"
