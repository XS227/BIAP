#!/usr/bin/env python3
"""BIAP Global v1 freeze: generate (--generate) or verify (default) the hash manifest.  Read-only: it only reads files, /proc/<pid>/environ of the
service and the public release endpoint.  Classes:
  exact      file bytes must be identical (code, config, units, release manifest, APKs, runner, tracked data)
  nginx      the Global-relevant nginx location blocks (the shared site file also carries Iran locations that change on Iran publishes)
  switches   effective decision-logic environment of the running service (v1 = DECISION_LOGIC_VERSION unset)
  endpoint   byte hash of the public Global release response
  append     daily snapshots: every file recorded at freeze must still be identical (new days may appear)
  inventory  mutable data refreshed by the existing timers: reported as INFO only (file count / bytes), never a failure
"""
import hashlib, json, os, re, subprocess, sys, urllib.request

PROD = "/home/ubuntu/biap-global/BIAP"
RUNNER = "/home/ubuntu/biap-snapshot-runner"
DATA = "/var/lib/biap-global"
DL = "/var/www/biap-global-web/download"
NGINX = "/etc/nginx/sites-available/biap-dadashi"
UNIT_GLOB = "/etc/systemd/system"
ENDPOINT = "https://biap.dadashi.no/global-api/app/release"
TAG = "global-v1-freeze-20261107"
SWITCH_KEYS = ["DECISION_MODE", "DECISION_LOGIC_VERSION", "BIAP_INVESTMENT_SCOPE", "BIAP_GLOBAL_ONLINE_FIRST", "BIAP_GLOBAL_RANKING_MARKETS", "BIAP_ANALYSIS_STALE_LABEL",
               "BIAP_YAHOO_CLOSE_STAMP", "BIAP_US_SESSION_DATE", "BIAP_EURONEXT_SESSION_DATE_MARKETS", "BIAP_GLOBAL_LIVE_TRADING_ENABLED"]
INVENTORY_DIRS = ["analysis-ledger", "cache", "fundamentals", "history", "market", "universe", "scan-cache", "shares", "source-index", "filings", "fx", "price-refresh-status", "sector-reference"]
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "reports", "v1_freeze_20261107.json")


def sh(cmd, cwd=None):
    if cmd and cmd[0] == "git":  # never take the index lock / refresh the index of a production clone
        cmd = ["git", "--no-optional-locks"] + cmd[1:]
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False, env=env).stdout


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def service_pid():
    return sh(["systemctl", "show", "biap-global", "-p", "MainPID", "--value"]).strip()


def switches():
    out = {}
    try:
        raw = open(f"/proc/{service_pid()}/environ", "rb").read().decode(errors="replace").split("\0")
    except OSError:
        return {"_error": "cannot read service environment"}
    env = dict(x.split("=", 1) for x in raw if "=" in x)
    for k in SWITCH_KEYS:
        out[k] = env.get(k)  # None = unset; none of these values is a secret
    return out


def nginx_blocks():
    text = open(NGINX, encoding="utf-8").read()
    blocks = {}
    for m in re.finditer(r"(?m)^( *)location [^\n{]*(?:/global-api/|/global/|/global )[^\n{]*\{.*?^\1\}", text, re.S | re.M):
        head = m.group(0).split("{", 1)[0].strip()
        blocks[head] = sha_text(re.sub(r"[ \t]+", " ", m.group(0)).strip())
    return blocks


def endpoint_hash():
    with urllib.request.urlopen(ENDPOINT, timeout=20) as r:
        return sha_text(r.read().decode("utf-8")), r.status


def collect():
    commit = sh(["git", "rev-parse", "HEAD"], PROD).strip()
    entries = []

    def add(cls, path, note=""):
        entries.append({"class": cls, "path": path, "sha256": sha(path), "size": os.path.getsize(path), "note": note})

    tracked = [p for p in sh(["git", "ls-files", "analysis"], PROD).split("\n") if p and not p.startswith("analysis/tests/")]
    for p in tracked:
        fp = os.path.join(PROD, p)
        if os.path.isfile(fp):
            add("exact", fp, "code/data tracked at " + commit[:7])
    dirty = [l[3:] for l in sh(["git", "status", "--short"], PROD).split("\n") if l.startswith(" M")]
    for p in dirty:
        head_blob = sh(["git", "show", f"HEAD:{p}"], PROD)
        for e in entries:
            if e["path"] == os.path.join(PROD, p):
                e["note"] = "LIVE working-tree file differs from the tag/HEAD (uncommitted); HEAD blob sha256 " + sha_text(head_blob)
    for l in sh(["git", "status", "--short", "--untracked-files=all", "analysis"], PROD).split("\n"):
        if l.startswith("??") and "__pycache__" not in l and ".venv" not in l:
            add("exact", os.path.join(PROD, l[3:]), "UNTRACKED file in the production clone")
    for extra in (".env.global",):  # config: hash only, never printed
        fp = os.path.join(PROD, "analysis", extra)
        if os.path.isfile(fp):
            add("exact", fp, "service environment file (contents never recorded)")
    for fn in sorted(os.listdir(UNIT_GLOB)):
        if fn.startswith("biap-global") and os.path.isfile(os.path.join(UNIT_GLOB, fn)):
            add("exact", os.path.join(UNIT_GLOB, fn), "systemd unit/timer")
    for root, _d, files in os.walk(UNIT_GLOB):
        if "biap-global" in root and root != UNIT_GLOB:
            for fn in sorted(files):
                add("exact", os.path.join(root, fn), "systemd drop-in")
    for fn in sorted(os.listdir(DL)):
        add("exact", os.path.join(DL, fn), "Global APK / download artifact")
    for p in [l for l in sh(["git", "ls-files"], RUNNER).split("\n") if l]:
        fp = os.path.join(RUNNER, p)
        if os.path.isfile(fp):
            add("exact", fp, "snapshot runner pinned clone @ " + sh(["git", "rev-parse", "--short", "HEAD"], RUNNER).strip())
    cron = [l for l in sh(["crontab", "-l"]).split("\n") if "run_daily_snapshot.sh" in l]
    freeze = {"commit": commit, "tag": TAG, "entries": entries, "dirtyTracked": dirty,
              "untrackedInProd": [l[3:] for l in sh(["git", "status", "--short"], PROD).split("\n") if l.startswith("??")],
              "switches": switches(), "nginx": nginx_blocks(), "cron": [sha_text(l) for l in cron], "cronLines": cron,
              "endpoint": dict(zip(("sha256", "status"), endpoint_hash())),
              "runnerHead": sh(["git", "rev-parse", "HEAD"], RUNNER).strip(),
              "pipFreezeSha256": sha_text(sh([os.path.join(PROD, "analysis/.venv-global/bin/python"), "-m", "pip", "freeze"])),
              "append": [], "inventory": {}}
    snap = os.path.join(DATA, "daily-snapshots")
    for root, _d, files in os.walk(snap):
        for fn in sorted(files):
            fp = os.path.join(root, fn)
            freeze["append"].append({"path": fp, "sha256": sha(fp), "size": os.path.getsize(fp)})
    for d in INVENTORY_DIRS:
        fp = os.path.join(DATA, d)
        n = b = 0
        for root, _x, files in os.walk(fp):
            for fn in files:
                n += 1
                try:
                    b += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
        freeze["inventory"][d] = {"files": n, "bytes": b}
    return freeze


def verify(freeze):
    cur = collect()
    bad, rows = 0, []

    def check(label, ok, detail=""):
        nonlocal bad
        rows.append(("PASS" if ok else "FAIL", label, detail))
        bad += 0 if ok else 1
    check("prod checkout HEAD", cur["commit"] == freeze["commit"], f"{cur['commit'][:7]} vs {freeze['commit'][:7]}")
    here = os.path.dirname(os.path.abspath(__file__))
    tagsha = sh(["git", "rev-list", "-n", "1", TAG], here).strip()
    remote = sh(["git", "ls-remote", "origin", f"refs/tags/{TAG}^{{}}", f"refs/tags/{TAG}"], here).strip()
    check(f"tag {TAG} -> frozen commit", tagsha == freeze["commit"], f"local {tagsha[:7] or 'missing'}; origin {'present' if remote else 'NOT pushed yet'}")
    old = {e["path"]: e for e in freeze["entries"]}; new = {e["path"]: e for e in cur["entries"]}
    changed = [p for p in old if p not in new or new[p]["sha256"] != old[p]["sha256"]]
    added = [p for p in new if p not in old and not p.endswith(".pyc")]
    check(f"exact files unchanged ({len(old)} files)", not changed, "; ".join(changed[:6]))
    check("no new files in the frozen sets", not added, "; ".join(added[:6]))
    check("service switches (v1 = DECISION_LOGIC_VERSION unset)", cur["switches"] == freeze["switches"], json.dumps({k: (freeze["switches"].get(k), cur["switches"].get(k)) for k in cur["switches"] if cur["switches"].get(k) != freeze["switches"].get(k)}))
    check("nginx Global blocks", cur["nginx"] == freeze["nginx"], "")
    check("snapshot cron line", cur["cron"] == freeze["cron"], "")
    check("snapshot runner HEAD", cur["runnerHead"] == freeze["runnerHead"], cur["runnerHead"][:7])
    check("Global release endpoint bytes", cur["endpoint"] == freeze["endpoint"], "")
    check("python environment (pip freeze)", cur["pipFreezeSha256"] == freeze["pipFreezeSha256"], "")
    a_old = {e["path"]: e["sha256"] for e in freeze["append"]}; a_new = {e["path"]: e["sha256"] for e in cur["append"]}
    check(f"daily snapshots: {len(a_old)} recorded files identical (new days allowed)", all(a_new.get(p) == h for p, h in a_old.items()), "")
    for r in rows:
        print(f"{r[0]:4}  {r[1]}  {r[2]}")
    print("\nINFO inventory (mutable data refreshed by the existing timers, not verified):")
    for d, v in cur["inventory"].items():
        o = freeze["inventory"].get(d, {})
        print(f"  {d:22} files {o.get('files')} -> {v['files']}   bytes {o.get('bytes')} -> {v['bytes']}")
    print("\nRESULT:", "FROZEN v1 UNCHANGED" if bad == 0 else f"{bad} CHECK(S) FAILED: v1 changed")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    path = os.path.abspath(MANIFEST)
    if "--generate" in sys.argv:
        data = collect(); json.dump(data, open(path, "w"), indent=1, ensure_ascii=False)
        print("written", path, len(data["entries"]), "exact entries")
    else:
        sys.exit(verify(json.load(open(path))))
