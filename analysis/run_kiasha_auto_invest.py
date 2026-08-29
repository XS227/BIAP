"""One-shot entrypoint for Kiasha Paper automation.

The systemd timer runs this periodically. It first processes user-submitted
manual Paper orders that were queued while TSE was closed, then runs due Auto
Invest users. Both paths are Paper-only; live trading is never enabled here.
"""

from __future__ import annotations

import json

from kiasha_auto_invest import run_due_auto_invest_users
from manual_paper_routes import process_due_manual_paper_orders


def main() -> None:
    payload = {
        "queuedManualOrders": process_due_manual_paper_orders(),
        "autoInvest": run_due_auto_invest_users(),
        "liveExecution": False,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
