"""Refresh the official Brazil CVM DFP cache."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .cvm import sync_cvm_dfp


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="*", type=int, default=None)
    args = parser.parse_args()
    years = args.years or [datetime.now(timezone.utc).year, datetime.now(timezone.utc).year - 1]
    result = sync_cvm_dfp(years=years)
    print(
        "CVM_SYNC:",
        f"records={result['recordCount']}",
        f"companies={result['companyKeys']}",
        f"sources={len(result['sources'])}",
        f"errors={','.join(result['errors']) if result['errors'] else 'none'}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
