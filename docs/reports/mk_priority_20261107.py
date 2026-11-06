"""Rebuild the CODAL request priority list: unverified originals first, then the 200 most-traded SHARES (no ETFs/funds) lacking an FY1402 annual statement,
then those that have it, then the top-60 by market cap (so large caps such as فملی are always requested), then the rest of the old list in its old order."""
import json, os, re, sys, shutil, datetime
sys.path.insert(0, "/home/ubuntu/wt-fix2/analysis"); sys.path.insert(0, "/home/ubuntu/claude-tmpdir/claude-1000/-home-ubuntu/5bb019d6-57d9-48f0-86cd-186e19caf748/scratchpad/full94")
os.environ.setdefault("BIAP_CODAL_INBOX", "/home/ubuntu/codal-inbox")
import module_dataset as md, codal_inbox, codal_reparse
from listed_company_store import ListedCompanyStore
from inbox_cov import filings_of
DB = "/home/ubuntu/biap-kiasha/XS227-BIAP/analysis/listed_companies.sqlite3"; PRI = "/home/ubuntu/codal-inbox/request/priority.txt"
sk = codal_inbox.symbol_key
rows = md.UNIVERSE.rows(ListedCompanyStore(DB))
old = [l.strip() for l in open(PRI, encoding="utf-8") if l.strip() and not l.startswith("#")]
kind_by_key = {sk(r["symbol"]): r.get("instrument_kind") for r in rows}
unver = [sk(d["symbol"]) for d in codal_reparse.reparse(DB)["details"] if d["status"] == "unverified" and kind_by_key.get(sk(d["symbol"]), "stock") == "stock"]
def tv(r): return r.get("trade_value") or ((r.get("volume") or 0) * (r.get("price") or 0))
shares = [r for r in rows if r.get("is_primary", 1) and r.get("instrument_kind") == "stock" and not r.get("sub_of") and r.get("category") not in ("bond_debt", "option_derivative", "fund_etf")
          and not str(r.get("name") or "").startswith("صندوق") and re.fullmatch(r"\d{12,}", str(r["code"]))]
top = sorted([r for r in shares if tv(r)], key=lambda r: -tv(r))[:200]
big = sorted([r for r in shares if r.get("market_cap")], key=lambda r: -r["market_cap"])[:60]
inbox = codal_inbox.current()
def has1402(r):
    key = sk(r["symbol"]); fl, _ = filings_of(key); usable = set(inbox.usable_tracing_nos(key)) if key in inbox.companies else set()
    return any(x["annual"] and x["fy"] == 1402 and x["tracing"] in usable for x in fl)
b1 = [r for r in top if not has1402(r)]; b2 = [r for r in top if has1402(r)]
order = []
for s in unver + [sk(r["symbol"]) for r in b1] + [sk(r["symbol"]) for r in b2] + [sk(r["symbol"]) for r in big] + [sk(o) for o in old if kind_by_key.get(sk(o), "stock") == "stock"]:
    if s and s not in order: order.append(s)
removed_funds = [o for o in old if o not in order]
if "--dry" not in sys.argv:
    shutil.copy(PRI, PRI + ".bak-" + datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S"))
    open(PRI, "w", encoding="utf-8").write("# priority symbols: unverified originals, top-200 shares lacking FY1402, FY1402-ready shares, top-60 by market cap, old list\n" + "\n".join(order) + "\n")
print(json.dumps({"unverified": len(unver), "top200_missing_1402": len(b1), "top200_have_1402": len(b2), "bigcaps": len(big), "total": len(order), "oldDropped": removed_funds,
                  "inList": {s: (s in order) for s in ("فملی", "فولاد", "شسینا", "وبملت", "خودرو", "وتجارت", "شستا")}}, ensure_ascii=False))
