"""One-shot entrypoint for the Kiasha Paper Auto Invest systemd timer.

Run this script periodically (for example every five minutes). The core runner
itself enforces Tehran trading days/window and one successful claim per user/day,
so repeated timer invocations are safe. It never enables live trading.
"""

from __future__ import annotations

import json

from kiasha_auto_invest import run_due_auto_invest_users


def main() -> None:
    print(json.dumps(run_due_auto_invest_users(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
