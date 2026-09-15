"""One-shot entrypoint for Kiasha Paper automation.

The systemd timer runs this periodically. It refreshes the cached whole-market
scan when stale, processes queued manual Paper orders, then runs due Auto Invest
users against Kiasha's Top-10 finalists. Claude/Sonnet is never used for the
full-universe scan and live trading is never enabled here.
"""

from __future__ import annotations

import json
import logging
import os
import sys

from deadline import DeadlineExceeded, run_with_deadline
from kiasha_auto_invest_v2 import refresh_market_scan, run_due_auto_invest_users
from manual_paper_routes import process_due_manual_paper_orders

logger = logging.getLogger("kiasha.runner")

# Every individual outbound call and every per-candidate stage already carries
# its own finite timeout (see deadline.py, kiasha_ai.py, market_data.py), but
# nothing previously bounded the market-scan/manual-order phases as a whole:
# the market scan alone can sequentially retry up to BIAP_MARKET_SCAN_DEEP_LIMIT
# candidates (default 12) at up to BIAP_MARKET_SCAN_DEEP_JOB_TIMEOUT_SECONDS
# each (up to 120s), which can already exceed this runner's own systemd timer
# interval (5 minutes) before Auto Invest even starts. These two ceilings bound
# those phases so one bad network day can never leave the oneshot systemd unit
# (which sets no TimeoutStartSec) running indefinitely.
#
# Auto Invest itself is deliberately NOT wrapped the same way here: it already
# enforces its own internal, cooperative KIASHA_AUTO_RUN_BUDGET_SECONDS budget
# per user (see kiasha_auto_invest._run_budget_seconds) that stops picking up
# *new* candidates once exceeded while keeping every already-computed result,
# including any real PAPER_FILLED trade. An outer run_with_deadline here would
# instead discard that entire (possibly successful) batch the moment the
# deadline ticks over, which is strictly worse.
MARKET_SCAN_TIMEOUT_SECONDS = max(30.0, float(os.getenv("KIASHA_RUNNER_MARKET_SCAN_TIMEOUT_SECONDS", "150")))
MANUAL_ORDERS_TIMEOUT_SECONDS = max(10.0, float(os.getenv("KIASHA_RUNNER_MANUAL_ORDERS_TIMEOUT_SECONDS", "30")))


def _run_stage(name: str, fn, *, timeout: float, on_error):
    """Run one bounded top-level phase (all-or-nothing on its own deadline).

    Only used for phases with no internal cooperative budget of their own
    (marketScan, queuedManualOrders). A phase that exceeds its deadline is
    recorded as a clear, structured failure and the runner continues with the
    remaining phases instead of aborting the whole cycle.
    """
    logger.info("runner stage_start stage=%s timeout=%.0fs", name, timeout)
    try:
        result = run_with_deadline(fn, timeout=timeout)
        logger.info("runner stage_done stage=%s", name)
        return result
    except DeadlineExceeded as exc:
        logger.warning("runner stage_TIMEOUT stage=%s: %s", name, exc)
        return on_error(f"stage timeout: {exc}")
    except Exception as exc:  # noqa: BLE001 - one phase failing must not abort the others
        logger.warning("runner stage_FAILED stage=%s: %s", name, str(exc)[:300])
        return on_error(str(exc)[:300])


def main() -> None:
    market_scan = _run_stage(
        "marketScan",
        refresh_market_scan,
        timeout=MARKET_SCAN_TIMEOUT_SECONDS,
        on_error=lambda reason: {"status": "ERROR", "top10": [], "errors": [reason]},
    )
    queued_manual_orders = _run_stage(
        "queuedManualOrders",
        process_due_manual_paper_orders,
        timeout=MANUAL_ORDERS_TIMEOUT_SECONDS,
        on_error=lambda reason: [{"status": "ERROR", "reason": reason}],
    )
    logger.info("runner stage_start stage=autoInvest")
    try:
        auto_invest = run_due_auto_invest_users()
        logger.info("runner stage_done stage=autoInvest")
    except Exception as exc:  # noqa: BLE001 - a single unexpected failure must not crash the whole cycle
        logger.warning("runner stage_FAILED stage=autoInvest: %s", str(exc)[:300])
        auto_invest = [{"status": "ERROR", "reason": str(exc)[:300]}]

    payload = {
        "marketScan": market_scan,
        "queuedManualOrders": queued_manual_orders,
        "autoInvest": auto_invest,
        "liveExecution": False,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        main()
    except Exception:
        logger.exception("runner FAILED unexpectedly")
        sys.exit(1)
