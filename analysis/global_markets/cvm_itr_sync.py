"""Refresh the official Brazil CVM ITR corroboration cache."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .cvm_itr import sync_cvm_itr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="*", type=int, default=None)
    args = parser.parse_args()
    year = datetime.now(timezone.utc).year
    years = args.years or [year, year - 1]
    result = sync_cvm_itr(years=years)
    print(
        "CVM_ITR_SYNC:",
        f"records={result['recordCount']}",
        f"companies={result['companyKeys']}",
        f"sources={len(result['sources'])}",
        f"errors={','.join(result['errors']) if result['errors'] else 'none'}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
