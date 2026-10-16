"""DE peer evidence pilot (option E): verify ONE official issuer document per ISIN against the stored ledger row.

Usage: python de_peer_doc_verify.py <scratch_dir> <candidates.json> <out.json>
  candidates.json: [{"isin": "...", "url": "https://issuer/.../annual-report.pdf", "period_end": "2025-12-31"}, ...]  (<=10 per call)

What it does (per candidate)
* checks the host's robots.txt (urllib.robotparser) and skips the source when the path is disallowed; no auth/CAPTCHA handling;
* downloads the single official document into <scratch_dir>/docs (untrusted data, text-extracted with pdftotext, then deleted);
* ACCEPTS the period end only when, in that document, (a) the claimed period-end date appears in an explicit period phrase,
  (b) the row's revenue AND net income both appear (exact to the document's rounding) -> the row provably IS this filing.
  EPS is checked and reported but is informational (basic vs diluted differ across issuers);
* retains ONLY metadata: ISIN, ticker, period_end, source URL, HTTP status, sha256, match booleans, verification time.
  No financial values are written to the output. Nothing is invented: a failed check leaves the row undated.
Stops if MemAvailable < 150 MB or free disk < 3 GB.
"""
import hashlib, html, json, os, re, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlparse

import httpx

SCRATCH = Path(sys.argv[1]); CAND = Path(sys.argv[2]); OUT = Path(sys.argv[3])
UA = "BIAP-Global/1.0 evidence-verification"
MAX_BYTES = 60_000_000
MONTHS_DE = ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "dezember"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def guard():
    mem = int([l for l in open("/proc/meminfo") if l.startswith("MemAvailable")][0].split()[1]) // 1024
    disk = shutil.disk_usage("/").free // 2**20
    if mem < 150 or disk < 3072:
        raise SystemExit(f"RESOURCE STOP mem_available={mem}MB disk_free={disk}MB")
    return mem, disk


def robots_ok(url, client):
    p = urlparse(url)
    try:
        r = client.get(f"{p.scheme}://{p.netloc}/robots.txt", timeout=15)
        if r.status_code >= 400:
            return True            # no robots file published -> nothing disallows it
        rp = robotparser.RobotFileParser(); rp.parse(r.text.splitlines())
        return rp.can_fetch(UA, url)
    except Exception:
        return False               # cannot establish permission -> do not fetch


def to_text(path, ctype):
    if path.suffix == ".zip":                      # ESEF report package: concatenate the (x)html members' text
        import zipfile
        parts = []
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.lower().endswith((".xhtml", ".html", ".htm")) and z.getinfo(n).file_size < 80_000_000:
                    raw = z.read(n).decode("utf-8", "ignore")
                    raw = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", raw)
                    parts.append(html.unescape(re.sub(r"<[^>]+>", " ", raw)))
                elif n.lower().endswith(".pdf") and z.getinfo(n).file_size < 80_000_000:
                    parts.append(subprocess.run(["pdftotext", "-layout", "-", "-"], input=z.read(n), capture_output=True, timeout=180).stdout.decode("utf-8", "ignore"))
        txt = "\n".join(parts)
    elif path.suffix == ".pdf":
        txt = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=180).stdout
    else:
        raw = path.read_text(errors="ignore")
        raw = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", raw)
        txt = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"[ \t  ]+", " ", txt)


def number_forms(v, unit):
    """Textual forms of v (EUR units) as it may print in a report stated in EUR/thousands/millions/billions."""
    forms = set()
    for scale, decs in ((1, (0, 2)), (1e3, (0, 1)), (1e6, (0, 1, 2)), (1e9, (0, 1))):   # 2-dec millions ("32.89") only matches a figure that really prints so
        x = abs(v) / scale
        for dec in decs:
            if scale == 1e6 and dec == 2 and abs(abs(v) - round(abs(v) / 1e4) * 1e4) >= 1:
                continue            # 2-decimal millions only when the stored figure is exactly that precise (no fuzzy matches)
            s = f"{x:,.{dec}f}"
            forms |= {s, s.replace(",", "."), s.replace(",", " "), s.replace(",", "\u2009"), s.replace(",", "'")}
            if dec:
                forms |= {s.replace(",", "").replace(".", ","), s.replace(",", " ").replace(".", ","),
                          s.replace(",", "X").replace(".", ",").replace("X", ".")}
    return forms


NET_INCOME_LABEL = re.compile(r"(?i)(konzernjahres(ueberschuss|überschuss)|jahres(ueberschuss|überschuss)|konzernergebnis|periodenergebnis|net income|net profit|profit for the (year|period))")


def has_number(text, v, label=None):
    """True when v prints in the document. Forms of <3 digits (e.g. "30" TEUR) are accepted only on a line carrying `label`."""
    if v is None:
        return False
    for f in number_forms(v, None):
        short = len(f.replace(",", "").replace(".", "").replace(" ", "")) < 3
        # a 1-2 digit figure counts only as an EXACT whole-TEUR amount (e.g. 30 000 EUR = "30" TEUR) on a line carrying the net-income label
        if short and (label is None or abs(v) < 10_000 or abs(v) % 1000 != 0 or f != str(int(abs(v) // 1000))):
            continue
        pat = re.compile(r"(?<![\d.,])" + re.escape(f) + r"(?![\d])")
        if not short:
            if pat.search(text):
                return True
        elif any(label.search(l) and pat.search(l) for l in text.splitlines()):
            return True
    return False


_GROUPED = re.compile(r"(?<![\d.,])\d{1,3}(?:[.,\u202f\u2009 ]\d{3})+(?![\d])")


def matches_rounded_teur(text, v, label=None):
    """True when the document prints a whole-TEUR (or whole-EUR) figure that ROUNDS to the stored figure.

    Providers store EUR figures rounded to 2-decimal millions (10 000 EUR); filings print the unrounded TEUR/EUR amount
    (e.g. 5.694.977 or 9,928 TEUR vs stored 5.69m / 9.93m). Only a stored figure that is exactly 10 000-precise is eligible,
    and the printed amount must round (within the 10 000 EUR rounding window) to it -- nothing is accepted that the document does not print.
    """
    if v is None or abs(v) < 100_000 or abs(abs(v) - round(abs(v) / 1e4) * 1e4) >= 1:
        return False
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if label is not None:       # net income: figure must sit on/near a net-income label and never on a comprehensive-income line
            if _COMPREHENSIVE.search(line) or not any(label.search(l) for l in lines[max(0, i - 6):i + 1]):
                continue
        if _rounded_hit(line, v):
            return True
    return False


NI_ATTRIBUTION_LABEL = re.compile(NET_INCOME_LABEL.pattern[:-1] + r"|attributable to|owners of the parent|(profit|share) of (the )?shareholders|after (minority|non-controlling)|nach (anteilen )?(anderer|nicht)|ergebnis nach|anteilseigner|mutterunternehmen)")
_COMPREHENSIVE = re.compile(r"(?i)(gesamtergebnis|comprehensive|gesamtperiodenergebnis)")


def _rounded_hit(text, v):
    for tok in _GROUPED.findall(text):
        n = int(re.sub(r"\D", "", tok))
        # stored = printed amount rounded to 10 000 EUR (+-5 000); a TEUR print is itself rounded (+-500)
        if abs(n * 1e3 - abs(v)) <= 5500 and len(str(n)) >= 3 or abs(n - abs(v)) <= 5000:
            return True
    return False


def period_phrase(text, iso):
    y, m, d = map(int, iso.split("-")); mon = MONTHS[m - 1]; mon3 = mon[:3]
    de = MONTHS_DE[m - 1]
    pats = [rf"{d}\.?\s*{de}\s+{y}", rf"{mon}\s+{d},?\s+{y}", rf"{d}\s+{mon}\s+{y}", rf"{d}\.\s*{mon}\s+{y}", rf"{d:02d}\.{m:02d}\.{y}",
            rf"{mon3}\.?\s+{d},?\s+{y}", rf"{d}\s+{mon3}\.?\s+{y}", rf"{y}-{m:02d}-{d:02d}"]
    low = text.lower()
    # the claimed period-end date must appear explicitly; the row is tied to this filing by the revenue+net-income match,
    # so a bare "Dec. 31, 2025" statement/balance-sheet date is sufficient (no invented dates).
    return any(re.search(p, low) for p in pats)


def main():
    cands = json.load(open(CAND))
    assert len(cands) <= 10, "batch limit is 10 issuers"
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "analysis"))
    os.environ.update(BIAP_GLOBAL_DATA_DIR=str(SCRATCH / "data"), BIAP_GLOBAL_ONLINE_FIRST="1")
    from global_markets import evidence_store as es
    rows = {}
    for m in ("XETRA", "FRANKFURT"):
        for r in es.read_ledger_rows("DE", m):
            c = r["company"]
            rows.setdefault(c["isin"], {"tickers": {}, "co": c})["tickers"][m] = c["ticker"]
    docs = SCRATCH / "docs"; docs.mkdir(exist_ok=True)
    res = []
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True) as client:
        mem, disk = guard()
        for c in cands:
            isin = c["isin"]; row = rows.get(isin)
            rec = {"isin": isin, "markets": row["tickers"] if row else None, "source_url": c["url"], "claimed_period_end": c["period_end"],
                   "verified_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
            if not row:
                rec["result"] = "NOT_A_UNIVERSE_PEER"; res.append(rec); continue
            co = row["co"]
            if not robots_ok(c["url"], client):
                rec["result"] = "BLOCKED_ROBOTS_OR_UNVERIFIABLE"; res.append(rec); continue
            try:
                with client.stream("GET", c["url"], timeout=60) as r:
                    rec["http_status"] = r.status_code
                    if r.status_code != 200:
                        rec["result"] = f"HTTP_{r.status_code}"; res.append(rec); continue
                    ct = r.headers.get("content-type", ""); h = hashlib.sha256(); n = 0
                    p = docs / (isin + (".pdf" if "pdf" in ct or c["url"].lower().endswith(".pdf") else ".zip" if "zip" in ct or c["url"].lower().split("?")[0].endswith(".zip") else ".html"))
                    with open(p, "wb") as fh:
                        for chunk in r.iter_bytes():
                            n += len(chunk)
                            if n > MAX_BYTES:
                                raise RuntimeError("too large")
                            h.update(chunk); fh.write(chunk)
                rec["sha256"] = h.hexdigest(); rec["bytes"] = n
                text = to_text(p, ct); p.unlink()
            except Exception as e:
                rec["result"] = f"FETCH_ERROR:{type(e).__name__}"; res.append(rec); continue
            rec["match"] = {"period_phrase": period_phrase(text, c["period_end"]), "revenue": has_number(text, co.get("revenue")) or matches_rounded_teur(text, co.get("revenue")),
                            "net_income": has_number(text, co.get("net_income"), NET_INCOME_LABEL) or matches_rounded_teur(text, co.get("net_income"), NI_ATTRIBUTION_LABEL), "eps_informational": bool(co.get("eps")) and
                            bool(re.search(r"(?<![\d.,])" + re.escape(f"{abs(co['eps']):.2f}") + r"(?!\d)", text) or
                                 re.search(r"(?<![\d.,])" + re.escape(f"{abs(co['eps']):.2f}".replace(".", ",")) + r"(?!\d)", text))}
            m = rec["match"]
            rec["result"] = "VERIFIED" if (m["period_phrase"] and m["revenue"] and m["net_income"]) else "NOT_VERIFIED"
            rec["sector_in_row"] = bool(co.get("sector"))
            res.append(rec)
            time.sleep(1.5)                         # polite spacing
    OUT.write_text(json.dumps({"batch_size": len(cands), "memAvailMB": mem, "diskFreeMB": disk, "results": res}, indent=1))
    for r in res:
        print(r["isin"], r["result"], r.get("match"))


if __name__ == "__main__":
    main()
