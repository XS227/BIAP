"""Opt-in, read-only BIAP Global intelligence endpoints.

The underlying analysis is exactly /global/analyze; this module only formats
its result. No independent signal, portfolio order, cache mutation, or model
generated financial claim is introduced.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from global_routes import InstrumentRequest, _seed
from global_markets.intelligence import build_company_dashboard, answer_company_question
from global_markets.service import analyze_company

router = APIRouter(prefix="/global/intelligence", tags=["BIAP Global Intelligence"])


class AnalystQuestion(BaseModel):
    instrument: InstrumentRequest
    question: str = Field(min_length=3, max_length=500)
    language: Literal["fa", "en"] = "fa"


def _analysis(instrument: InstrumentRequest) -> dict:
    try:
        return analyze_company(_seed(instrument))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Global analysis unavailable") from exc


@router.post("/dashboard")
def intelligence_dashboard(instrument: InstrumentRequest):
    """Financial KPI snapshot with evidence and per-field attribution warnings."""
    return build_company_dashboard(_analysis(instrument))


@router.post("/ask")
def intelligence_ask(req: AnalystQuestion):
    """Grounded per-company Q&A, not unrestricted LLM chat or a stock screener."""
    dashboard = build_company_dashboard(_analysis(req.instrument))
    return answer_company_question(dashboard, req.question, req.language)
