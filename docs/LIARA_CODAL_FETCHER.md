# Liara CODAL fetcher: install guide

Liara (89.42.199.20) can reach codal.ir; the BIAP VPS (5.249.252.88) cannot. Liara fetches, then `scp`s
dated folders to `/home/ubuntu/codal-inbox/` on the VPS. Python 3.7+ standard library only, run as root.

**1. Get the script onto Liara** (either one)
```
curl -fsSL https://raw.githubusercontent.com/XS227/BIAP/feat/liara-codal-relay-20261024/tools/liara_codal_fetcher.py \
  -o /root/liara_codal_fetcher.py && chmod 755 /root/liara_codal_fetcher.py
# or: git clone -b feat/liara-codal-relay-20261024 https://github.com/XS227/BIAP.git /root/BIAP   (script: /root/BIAP/tools/)
```
After the branch is merged, replace the branch name with `main`.

**2. Check the three prerequisites**
```
python3 --version                                   # 3.7 or newer
curl -s -o /dev/null -w '%{http_code}\n' https://search.codal.ir/api/search/v1/financialYears?Symbol=%D9%81%D9%88%D9%84%D8%A7%D8%AF   # expect 200
ssh -i /root/.ssh/id_ed25519 -o BatchMode=yes ubuntu@5.249.252.88 true && echo ssh-ok
```

**3. Test run on 3 companies, no upload** (about 2 minutes; `--symbols` never touches the new-filings cursor)
```
/root/liara_codal_fetcher.py --symbols "فولاد,شپنا,خودرو" --no-upload
cat /root/codal-export/$(date -u +%F)/manifest.json | head -30
```
Expect `"ok": 3` (or `no_data` for a symbol CODAL really has nothing on). Any `"error"` is a real failure; the
reason is in `error_samples` and on stderr. Then test the upload with the same folder:
```
scp -r -i /root/.ssh/id_ed25519 /root/codal-export/$(date -u +%F) ubuntu@5.249.252.88:/home/ubuntu/codal-inbox/
```
(On the VPS the importer will verify it. It stays unused until `BIAP_CODAL_INBOX` is set on the job.)

**4. Root crontab at 00:15 UTC** (`crontab -e`)
```
CRON_TZ=UTC
15 0 * * * /usr/bin/python3 /root/liara_codal_fetcher.py >> /root/codal-fetcher.log 2>&1
```
If `date` on Liara is not UTC and your cron ignores `CRON_TZ`, use the local hour for 00:15 UTC instead.

The cron run pulls its company list from the VPS (`/home/ubuntu/codal-inbox/request/symbols.txt`, written by
`codal_inbox.py request` there), checks new financial filings since its last cursor, fetches those first and then
the backlog, and uploads. The default is one request per 12 s (`--interval`); every 429 doubles the interval for the rest of that run (cap 60 s). 3 hours (`--max-seconds`) therefore covers roughly 50-150 companies; it resumes
the same day if re-run. Exit codes: 0 complete, 3 partial but uploaded (e.g. CODAL 429s), 1 upload failed, 2 no list, 75 already running.

**Not verified live:** CODAL was unreachable from the dev host, so the request shapes (page length 12, a
`FromDate` of 1380/01/01 for per-symbol searches) follow the existing BIAP code but were only tested against
fakes. Step 3 is the first real check.
