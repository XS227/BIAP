#!/usr/bin/env python3
"""Generate and persist the weekly grounded TSE/IFB market report."""
from __future__ import annotations

import json
import os
from pathlib import Path

from market_memory import latest_weekly_market_report


def main() -> int:
    try:
        days = max(1, int(os.getenv("BIAP_WEEKLY_MARKET_WINDOW_DAYS", "7")))
    except ValueError:
        days = 7
    report = latest_weekly_market_report(days=days)
    output = os.getenv("BIAP_WEEKLY_MARKET_REPORT_JSON", "").strip()
    if output:
        path = Path(output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    # Zero observations are a valid fail-soft report while the history store is
    # warming; coverage metadata makes that explicit rather than inventing data.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
