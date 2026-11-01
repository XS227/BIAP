"""Authenticated, read-only company endpoints for the Iranian app (stored data only)."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query

import iran_company_view as view
from auth import require_user_id

router = APIRouter(prefix="/iran", tags=["BIAP Iran"])

def _require_checkpoint_flag(name: str) -> None:
    """Keep these routes off in production unless an isolated staging API opts in."""
    if os.environ.get(name, "").strip() != "1":
        raise HTTPException(status_code=404, detail="Development-only route disabled")



def _guard(fn, *args):
    try:
        return fn(*args)
    except view.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/company/stored")
def iran_company_stored(q: str = Query(..., min_length=1, max_length=64), _user: str = Depends(require_user_id)):
    """Stored view: seven agents, latest Kiasha run, price with provenance, CODAL statements, ratios."""
    _require_checkpoint_flag("BIAP_CHECKPOINT_IRAN_READONLY")
    return _guard(view.company_view, q)


@router.get("/company/audit")
def iran_company_audit(q: str = Query(..., min_length=1, max_length=64), _user: str = Depends(require_user_id)):
    _require_checkpoint_flag("BIAP_CHECKPOINT_IRAN_READONLY")
    return _guard(view.audit_checks, q)


@router.post("/company/ai-analysis")
def iran_company_ai(q: str = Query(..., min_length=1, max_length=64), user_id: str = Depends(require_user_id)):
    _require_checkpoint_flag("BIAP_CHECKPOINT_IRAN_READONLY")
    _require_checkpoint_flag("BIAP_CHECKPOINT_IRAN_AI")
    try:
        return view.ai_report(q, user_id)
    except view.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except view.RateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "3600"}) from exc
    except view.AIUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
