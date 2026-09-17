"""Standalone BIAP Global API application.

Run this independently from the Iran production service while Global is under
development. This preserves the existing `/api/stock/*` production contract and
lets the mobile/web client point to a separate staging origin.
"""

from fastapi import FastAPI

from global_routes import router as global_router
from global_source_routes import router as global_source_router


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
    }
