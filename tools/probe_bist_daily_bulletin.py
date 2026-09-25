from __future__ import annotations
from datetime import date, timedelta
from io import BytesIO
import zipfile
import requests

UA = "BIAP Global official BIST probe (+https://setai.no)"
s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept": "*/*"})

for delta in range(0, 8):
    d = date.today() - timedelta(days=delta)
    y=d.strftime("%Y"); m=d.strftime("%m"); ymd=d.strftime("%Y%m%d")
    url=f"https://borsaistanbul.com/data/thb/{y}/{m}/thb{ymd}1.zip"
    try:
        r=s.get(url, timeout=10, allow_redirects=True)
        print("TRY", d.isoformat(), r.status_code, len(r.content), r.url)
        if r.status_code != 200 or len(r.content) < 100 or r.content[:2] != b"PK":
            continue
        z=zipfile.ZipFile(BytesIO(r.content))
        print("SUCCESS", url)
        print("FILES", z.namelist())
        for name in z.namelist()[:3]:
            raw=z.read(name)
            for enc in ("utf-8-sig","cp1254","iso-8859-9"):
                try:
                    text=raw[:8000].decode(enc)
                    break
                except UnicodeDecodeError:
                    text=""
            print("SAMPLE", name)
            print("\n".join(text.splitlines()[:12]))
        raise SystemExit(0)
    except requests.RequestException as exc:
        print("ERR", type(exc).__name__, str(exc)[:160])
raise SystemExit("No BIST official daily bulletin found for the last 8 calendar days")
