#!/bin/bash
# Runs on LIARA (root).  Pulls the newest UniWeb daily backup into /root/uniweb-backups/biap-global-YYYY-MM-DD.
# Needs 2x backup size + 5 GB free first; keeps the 2 newest biap-global-* copies; touches nothing else there.
# Cron (Mon 02:00 UTC):  0 2 * * 1 /root/liara-pull.sh >> /var/log/biap-liara-pull.log 2>&1
set -u
S=${PULL_SRC:-ubuntu@5.249.252.88}; B=${PULL_SRC_DIR:-/home/ubuntu/backups/daily}; D=${PULL_DEST:-/root/uniweb-backups}
KEY=${PULL_KEY:-/root/.ssh/id_ed25519}; EXTRA=${PULL_MIN_FREE_KB:-5242880}
O="-i $KEY -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=20"
log() { echo "$(date -u +%FT%TZ) $*"; }
exec 9>/run/biap-pull.lock 2>/dev/null || exec 9>"$D.lock"; flock -n 9 || { log "SKIP: already running"; exit 75; }
mkdir -p "$D"
L=$(ssh $O "$S" "ls -1 $B | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}\$' | sort | tail -1") && [ -n "$L" ] || { log "FAIL: no backup / ssh"; exit 1; }
K=$(ssh $O "$S" "du -sk $B/$L | cut -f1") && [[ "$K" =~ ^[0-9]+$ ]] || { log "FAIL: du"; exit 1; }
F=$(df -Pk "$D" | awk 'NR==2{print $4}'); NEED=$((K*2+EXTRA))
[ "$F" -ge "$NEED" ] || { log "FAIL: low space free_kb=$F need_kb=$NEED"; exit 1; }
rsync -a --partial -e "ssh $O" "$S:$B/$L/" "$D/biap-global-$L.partial/" || { log "FAIL: rsync"; exit 1; }
rm -rf "$D/biap-global-$L" && mv "$D/biap-global-$L.partial" "$D/biap-global-$L"
ls -1d "$D"/biap-global-????-??-?? | sort | head -n -2 | xargs -r rm -rf --
log "OK biap-global-$L; now: $(ls -1d "$D"/biap-global-* | tr '\n' ' ')"
