"""Standalone BIAP Global API application.

Run this independently from the Iran production service while Global is under
development. This preserves the existing `/api/stock/*` production contract and
lets the mobile/web client point to a separate staging origin.
"""

from pathlib import Path
import subprocess

from fastapi import FastAPI

from global_routes import router as global_router
from global_source_routes import router as global_source_router


def _running_commit() -> str | None:
    """Commit of the checkout this process was started from (read once)."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


RUNNING_COMMIT = _running_commit()

app = FastAPI(title="BIAP Global research service")
app.include_router(global_router)
app.include_router(global_source_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "biap-global",
        "liveTrading": False,
        "productionIranModified": False,
        "commit": RUNNING_COMMIT,
    }
