#!/bin/bash
# Run ON LIARA (root). Applies the PR #99 fetcher (merged to main 9320f8b). The change is limited to what was approved:
#   3 annual fiscal years + latest statement per company, 429 backoff + 6 h cooldown, skip already-shipped reports, optional --max-requests.
# (default request interval 12 s -> 20 s; request-list order logic and the cron line are NOT changed.)
set -euo pipefail
TS=$(date -u +%Y%m%dT%H%M%SZ)
cd /root
cp -a /root/liara_codal_fetcher.py "/root/liara_codal_fetcher.py.bak-$TS"       # rollback copy of the current job
crontab -l > "/root/crontab.bak-$TS"
curl -fsSL https://raw.githubusercontent.com/XS227/BIAP/9320f8b/tools/liara_codal_fetcher.py -o /root/liara_codal_fetcher.py.new
python3 -c "import ast; ast.parse(open('/root/liara_codal_fetcher.py.new').read())"
grep -q "^ANNUAL_YEARS = 3" /root/liara_codal_fetcher.py.new && grep -q "COOLDOWN_HOURS" /root/liara_codal_fetcher.py.new
python3 /root/liara_codal_fetcher.py.new --help >/dev/null
sha256sum /root/liara_codal_fetcher.py.new
chmod 755 /root/liara_codal_fetcher.py.new
mv /root/liara_codal_fetcher.py.new /root/liara_codal_fetcher.py
echo "applied. Old job kept: /root/liara_codal_fetcher.py.bak-$TS"
echo "ROLLBACK: cp -a /root/liara_codal_fetcher.py.bak-$TS /root/liara_codal_fetcher.py"
echo "Optional (spread the budget): add --max-requests 40 to the cron line and run it 4x/day outside 22:45-02:00 UTC (see docs)."
