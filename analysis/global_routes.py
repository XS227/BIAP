"""FastAPI routes for BIAP Global.

Global routes are isolated from the existing Iran `/stock/*` contract. They can
evolve independently while the Iran production endpoints stay intact.
"""
from __future__ import annotations

from dataclasses import asdict
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from global_markets.country_packs import country_catalog, get_exchange
from global_markets.models import InvestorProfile
from global_markets.runtime import build_registry
from global_markets.scan_service import scan_global_market
from global_markets.service import analyze_company, instrument_seed, portfolio_from_instruments
from global_markets.source_catalog import SOURCE_PLANS, requirements_payload

router = APIRouter(prefix="/global", tags=["BIAP Global"])


class InstrumentRequest(BaseModel):
    country: str = Field(min_length=2, max_length=2)
    exchange: str = Field(min_length=2, max_length=64)
    ticker: str = Field(min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, max_length=200)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    isin: Optional[str] = Field(default=None, min_length=8, max_length=16)
    lei: Optional[str] = Field(default=None, min_length=20, max_length=20)


class ScanRequest(BaseModel):
    country: str = Field(min_length=2, max_length=2)
    exchange: str = Field(min_length=2, max_length=64)
    topN: int = Field(default=10, ge=1, le=50)
    discoveryLimit: int = Field(default=1000, ge=10, le=5000)
    deepLimit: int = Field(default=25, ge=1, le=100)


class PortfolioProfileRequest(BaseModel):
    capital: float = Field(gt=0)
    baseCurrency: str = Field(min_length=3, max_length=3)
    riskTolerance: str = Field(default="medium", min_length=2, max_length=32)
    horizon: str = Field(default="5y", min_length=1, max_length=32)
    allowedCountries: list[str] = Field(default_factory=list, max_length=40)
    allowedExchanges: list[str] = Field(default_factory=list, max_length=80)
    maxPositionPct: float = Field(default=10.0, gt=0, le=100)
    maxCountryPct: float = Field(default=40.0, gt=0, le=100)
    maxSectorPct: float = Field(default=30.0, gt=0, le=100)
    minCashReservePct: float = Field(default=10.0, ge=0, lt=100)
    maxPositions: int = Field(default=10, ge=1, le=50)


class PortfolioRequest(BaseModel):
    profile: PortfolioProfileRequest
    instruments: list[InstrumentRequest] = Field(min_length=1, max_length=50)
    fxToBase: dict[str, float] = Field(default_factory=dict)


def _seed(req: InstrumentRequest):
    try:
        return instrument_seed(
            country=req.country,
            exchange=req.exchange,
            ticker=req.ticker,
            name=req.name,
            currency=req.currency,
            isin=req.isin,
            lei=req.lei,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/countries")
def global_countries():
    catalog = country_catalog()
    return {"count": len(catalog), "countries": catalog}


@router.get("/instruments/{country}/{exchange}")
def global_instruments(
    country: str,
    exchange: str,
    q: Optional[str] = Query(default=None, max_length=80),
    limit: int = Query(default=100, ge=1, le=1000),
):
    try:
        spec = get_exchange(country, exchange)
        registry = build_registry()
        provider = registry.universe(country, spec.code)
        instruments = list(provider.list_instruments(country=country.upper(), exchange=spec.code))
        snapshot_info = None
        if hasattr(provider, "snapshot_info"):
            try:
                snapshot_info = provider.snapshot_info(country=country.upper(), exchange=spec.code)
            except Exception:
                snapshot_info = None
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:500]) from exc
    if q:
        wanted = q.casefold().strip()
        instruments = [item for item in instruments if (
            wanted in item.ticker.casefold()
            or wanted in item.name.casefold()
            or (item.isin and wanted in item.isin.casefold())
            or (item.lei and wanted in item.lei.casefold())
        )]
    total = len(instruments)
    return {
        "country": country.upper(),
        "exchange": spec.code,
        "mic": spec.mic,
        "totalMatched": total,
        "returned": min(total, limit),
        "catalog": snapshot_info,
        "instruments": [asdict(item) for item in instruments[:limit]],
    }


@router.get("/requirements")
def global_requirements():
    return {"requirements": requirements_payload(), "sources": SOURCE_PLANS}


@router.get("/status")
def global_status():
    live_switch_requested = os.environ.get("BIAP_GLOBAL_LIVE_TRADING_ENABLED", "false").strip().lower() == "true"
    return {
        "mode": "research-paper-first",
        "liveTrading": False,
        "liveBrokerConnected": False,
        "liveTradingSwitchRequested": live_switch_requested,
        "marketProviderConfigured": bool(os.environ.get("BIAP_GLOBAL_MARKET_API_KEY")),
        "secConfigured": bool(os.environ.get("BIAP_SEC_USER_AGENT")),
        "openDartConfigured": bool(os.environ.get("BIAP_OPENDART_API_KEY")),
        "edinetConfigured": bool(os.environ.get("BIAP_EDINET_API_KEY")),
        "companiesHouseConfigured": bool(os.environ.get("BIAP_COMPANIES_HOUSE_API_KEY")),
        "esefConfigured": True,
        "iranBridgeConfigured": True,
        "universeCacheConfigured": True,
        "universeCacheHours": float(os.environ.get("BIAP_GLOBAL_UNIVERSE_CACHE_HOURS", "12")),
        "countries": len(country_catalog()),
        "notes": "No live global broker is connected. Missing/stale evidence is never fabricated and can force NO_RECOMMENDATION.",
    }


@router.post("/scan")
def global_scan(req: ScanRequest):
    try:
        get_exchange(req.country, req.exchange)
        return scan_global_market(
            country=req.country,
            exchange=req.exchange,
            top_n=req.topN,
            discovery_limit=req.discoveryLimit,
            deep_limit=req.deepLimit,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:500]) from exc


@router.post("/analyze")
def global_analyze(req: InstrumentRequest):
    try:
        return analyze_company(_seed(req))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:500]) from exc


@router.post("/portfolio")
def global_portfolio(req: PortfolioRequest):
    profile = InvestorProfile(
        capital=req.profile.capital,
        base_currency=req.profile.baseCurrency.upper(),
        risk_tolerance=req.profile.riskTolerance,
        horizon=req.profile.horizon,
        allowed_countries=tuple(value.upper() for value in req.profile.allowedCountries),
        allowed_exchanges=tuple(value.upper() for value in req.profile.allowedExchanges),
        max_position_pct=req.profile.maxPositionPct,
        max_country_pct=req.profile.maxCountryPct,
        max_sector_pct=req.profile.maxSectorPct,
        min_cash_reserve_pct=req.profile.minCashReservePct,
        max_positions=req.profile.maxPositions,
    )
    instruments = [_seed(item) for item in req.instruments]
    fx = {currency.upper(): float(rate) for currency, rate in req.fxToBase.items() if float(rate) > 0}
    try:
        return portfolio_from_instruments(profile, instruments, fx_to_base=fx)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:500]) from exc
