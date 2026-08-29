"""One-shot entrypoint for Kiasha Paper automation.

The systemd timer runs this periodically. It refreshes the cached whole-market
scan when stale, processes queued manual Paper orders, then runs due Auto Invest
users against Kiasha's Top-10 finalists. Claude/Sonnet is never used for the
full-universe scan and live trading is never enabled here.
"""

from __future__ import annotations

import json

from kiasha_auto_invest_v2 import refresh_market_scan, run_due_auto_invest_users
from manual_paper_routes import process_due_manual_paper_orders


def main() -> None:
    payload = {
        "marketScan": refresh_market_scan(),
        "queuedManualOrders": process_due_manual_paper_orders(),
        "autoInvest": run_due_auto_invest_users(),
        "liveExecution": False,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
