from __future__ import annotations
from datetime import date, timedelta
from io import BytesIO
import zipfile
import requests

UA = "BIAP Global official BIST probe (+https://setai.no)"
session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept": "*/*"})

candidates = []
today = date.today()
for delta in range(0, 10):
    d = today - timedelta(days=delta)
    y=d.strftime("%Y"); m=d.strftime("%m"); ymd=d.strftime("%Y%m%d")
    candidates.extend([
        f"https://borsaistanbul.com/data/thb/{y}/{m}/thb{ymd}S.zip",
        f"https://www.borsaistanbul.com/data/thb/{y}/{m}/thb{ymd}S.zip",
        f"https://borsaistanbul.com/data/thb/{y}/{m}/thb{ymd}.zip",
        f"https://www.borsaistanbul.com/data/thb/{y}/{m}/thb{ymd}.zip",
    ])

for url in candidates:
    try:
        r=session.get(url, timeout=30, allow_redirects=True)
        print("TRY", r.status_code, len(r.content), r.url)
        if r.status_code != 200 or len(r.content) < 100:
            continue
        if r.content[:2] != b"PK":
            print("NOTZIP", r.headers.get("content-type"), r.text[:120].replace("\n"," "))
            continue
        z=zipfile.ZipFile(BytesIO(r.content))
        print("SUCCESS", url)
        print("FILES", z.namelist()[:20])
        for name in z.namelist()[:3]:
            raw=z.read(name)
            print("SAMPLE", name, raw[:1200].decode("utf-8", errors="replace"))
        break
    except Exception as exc:
        print("ERR", type(exc).__name__, str(exc)[:180], url)
else:
    raise SystemExit("No official BIST THB daily bulletin ZIP found in last 10 days")
