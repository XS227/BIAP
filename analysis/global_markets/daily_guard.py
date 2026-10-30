"""Daily live guard: flag markets that silently lost all BUY/SELL calls or whose BLOCK count jumped.

Runs from biap-global-daily-guard.timer at 23:00 UTC (before the 23:40 snapshot).  Read-only on the
ledgers; it only writes its own per-day count file under ``<data dir>/guard``.  Exit 1 on any finding.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Dict, List, Optional

log = logging.getLogger("biap.daily_guard")

# The 13 price-refresh markets minus DE:FRANKFURT (provisional).  Override with BIAP_GUARD_MARKETS="CC:EXCH CC:EXCH ...".
DEFAULT_MARKETS = (
    "US:NASDAQ", "US:NYSE", "GB:LSE", "DE:XETRA", "FR:EURONEXT_PARIS", "IT:EURONEXT_MILAN",
    "ES:BME_MADRID", "NL:EURONEXT_AMSTERDAM", "SE:NASDAQ_STOCKHOLM", "NO:EURONEXT_OSLO",
    "DK:NASDAQ_COPENHAGEN", "FI:NASDAQ_HELSINKI",
)
BLOCK_RISE_LIMIT = 0.20
ALERT_TO = "nasrindadashiwin@gmail.com"

Counts = Dict[str, int]


class OutOfScope(Exception):
    """Market is outside the investment-mode scope: it has no tiers by design, so it is skipped, not alarmed."""


def data_dir() -> Path:
    return Path(os.environ.get("BIAP_GLOBAL_DATA_DIR", "/var/lib/biap-global"))


def markets() -> List[str]:
    raw = os.environ.get("BIAP_GUARD_MARKETS", "").split()
    return raw or list(DEFAULT_MARKETS)


def block_count(ledger: Path) -> int:
    con = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        return int(con.execute("SELECT COUNT(*) FROM ledger WHERE evidence_status = 'BLOCK'").fetchone()[0])
    finally:
        con.close()


def collect_market(code: str) -> Counts:
    """{'BUY','SELL','BLOCK'} for one ``CC:EXCH`` from the live ledger and the investment-tier overlay."""
    from global_markets import decision_overlay as overlay
    from global_markets import investment_mode as im

    country, exchange = code.split(":", 1)
    if im.decision_mode() != im.INVESTMENT:
        raise RuntimeError("investment mode is off (DECISION_MODE / .env.global not loaded?)")
    if not im.in_scope(code):
        raise OutOfScope(code)
    tiers = overlay.tier_counts(overlay.market_view(country, exchange))
    ledger = data_dir() / "analysis-ledger" / f"{country}__{exchange}.sqlite3"
    return {"BUY": tiers.get("BUY", 0), "SELL": tiers.get("SELL", 0), "BLOCK": block_count(ledger)}


def evaluate(today: Dict[str, Optional[Counts]], yesterday: Optional[Dict[str, Counts]]) -> List[str]:
    """Return the list of WARNING lines; empty means healthy.  ``None`` for a market = unreadable."""
    problems: List[str] = []
    for code, now in today.items():
        if now is None:
            problems.append(f"{code}: UNREADABLE (ledger or tier view failed)")
            continue
        for tier in ("BUY", "SELL"):
            if now.get(tier, 0) == 0:
                problems.append(f"{code}: {tier} count is 0")
        before = (yesterday or {}).get(code)
        if before is not None:
            was, is_ = before.get("BLOCK", 0), now.get("BLOCK", 0)
            if is_ > was * (1 + BLOCK_RISE_LIMIT):
                problems.append(f"{code}: BLOCK rose {was} -> {is_} (limit +{int(BLOCK_RISE_LIMIT * 100)}%)")
    return problems


def _load_previous(directory: Path, today: date) -> Optional[Dict[str, Counts]]:
    days = sorted(p for p in directory.glob("????-??-??.json") if p.stem < today.isoformat())
    if not days:
        return None
    try:
        return json.loads(days[-1].read_text())
    except (OSError, ValueError):
        return None


def send_alert(subject: str, body: str, which: Callable[[str], Optional[str]] = shutil.which,
               run: Callable = subprocess.run) -> bool:
    """Email via the local sendmail if one exists; otherwise only log.  Returns True when handed to the MTA."""
    sendmail = which("sendmail")
    if not sendmail:
        log.warning("mail not configured (no sendmail); alert logged only")
        return False
    msg = EmailMessage()
    msg["To"], msg["Subject"] = ALERT_TO, subject
    msg.set_content(body)
    try:
        run([sendmail, "-t", "-i"], input=msg.as_bytes(), check=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("alert email failed: %s", exc)
        return False
    return True


def run_guard(collect: Callable[[str], Counts] = collect_market, today: Optional[date] = None,
              directory: Optional[Path] = None, mail: Callable[[str, str], bool] = send_alert) -> int:
    today = today or datetime.now(timezone.utc).date()
    directory = directory or data_dir() / "guard"
    directory.mkdir(parents=True, exist_ok=True)
    current: Dict[str, Optional[Counts]] = {}
    for code in markets():
        try:
            current[code] = collect(code)
        except OutOfScope:
            log.info("%s: not in investment scope, skipped", code)
        except Exception as exc:  # one bad market must not hide the others
            log.warning("%s: collect failed: %s", code, exc)
            current[code] = None
    problems = evaluate(current, _load_previous(directory, today))
    (directory / f"{today.isoformat()}.json").write_text(
        json.dumps({k: v for k, v in current.items() if v is not None}, sort_keys=True))
    for code, c in current.items():
        if c is not None:
            log.info("%s BUY=%d SELL=%d BLOCK=%d", code, c["BUY"], c["SELL"], c["BLOCK"])
    if problems:
        for line in problems:
            log.warning("GUARD %s", line)
        mail(f"BIAP Global guard: {len(problems)} problem(s) {today}", "\n".join(problems))
        return 1
    log.info("GUARD ok: %d markets", len(current))
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)
    return run_guard()


if __name__ == "__main__":
    sys.exit(main())
