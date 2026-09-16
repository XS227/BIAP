"""CLI for updating the Japan EDINET annual-report index on the Global server.

Example:
  PYTHONPATH=analysis python -m global_markets.edinet_sync --days 450
Daily timer after bootstrap:
  PYTHONPATH=analysis python -m global_markets.edinet_sync --days 3
"""
from __future__ import annotations

import argparse
import json

from .edinet import sync_edinet_index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3)
    args = parser.parse_args()
    result = sync_edinet_index(days=args.days)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result.get("errors") else 2


if __name__ == "__main__":
    raise SystemExit(main())
