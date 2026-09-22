"""Normalized data contracts for BIAP Global.

The global core never assumes a specific exchange, regulator or filing format.
Provider adapters normalize verified source data into these contracts before any
agent is allowed to score an instrument.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SourceEvidence:
    provider: str
    source_type: str
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    observed_at: Optional[str] = None
    period_end: Optional[str] = None
    quality: float = 1.0
    notes: Optional[str] = None


@dataclass
class GlobalCompany:
    # Stable instrument/entity identity. Exchange/MIC identifies the listing;
    # ISIN identifies the security; LEI identifies the legal reporting entity.
    country: str
    exchange: str
    currency: str
    ticker: str
    name: str
    mic_code: Optional[str] = None
    isin: Optional[str] = None
    lei: Optional[str] = None
    instrument_type: str = "Common Stock"
    sector: Optional[str] = None
    industry: Optional[str] = None
    reporting_currency: Optional[str] = None
    lot_size: Optional[int] = None

    # Market state and history. Prices must be split-adjusted when a provider
    # supplies adjusted history; the adapter records that fact in provenance.
    price: Optional[float] = None
    price_observed_at: Optional[str] = None
    volume_today: Optional[float] = None
    avg_volume_30d: Optional[float] = None
    market_cap: Optional[float] = None
    shares_outstanding: Optional[float] = None
    price_52w_high: Optional[float] = None
    price_52w_low: Optional[float] = None
    volatility_annualized_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    return_1m_pct: Optional[float] = None
    return_3m_pct: Optional[float] = None
    return_6m_pct: Optional[float] = None
    beta: Optional[float] = None

    # Valuation and shareholder return.
    pe: Optional[float] = None
    sector_pe: Optional[float] = None
    pb: Optional[float] = None
    ev_ebitda: Optional[float] = None
    dividend_yield_pct: Optional[float] = None
    dividend_per_share: Optional[float] = None
    eps: Optional[float] = None
    book_value_per_share: Optional[float] = None

    # Normalized filing fundamentals. Values stay in reporting_currency and
    # must not be mixed across consolidated/standalone scope by an adapter.
    revenue: Optional[float] = None
    revenue_prev: Optional[float] = None
    revenue_yoy_pct: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    ebitda: Optional[float] = None
    net_income: Optional[float] = None
    net_margin_pct: Optional[float] = None
    net_margin_prev_pct: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_equity: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    free_cash_flow: Optional[float] = None
    total_debt: Optional[float] = None
    interest_expense: Optional[float] = None

    # Filing/evidence controls.
    audit_opinion: Optional[str] = None
    filing_period_end: Optional[str] = None
    filing_observed_at: Optional[str] = None
    report_scope: Optional[str] = None
    restatement_flag: Optional[bool] = None
    material_event_flags: tuple[str, ...] = ()
    sources: list[SourceEvidence] = field(default_factory=list)
    raw_provider_fields: dict = field(default_factory=dict)

    def identity(self) -> str:
        venue = (self.mic_code or self.exchange).upper()
        return f"{self.country.upper()}:{venue}:{self.ticker}"


@dataclass(frozen=True)
class AgentSignal:
    agent: str
    vote: float
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class EvidenceAssessment:
    status: str
    confidence_multiplier: float
    coverage: float
    freshness_score: float
    contradictions: tuple[str, ...] = ()
    missing_critical: tuple[str, ...] = ()
    reasoning: str = ""

    @property
    def blocked(self) -> bool:
        return self.status == "BLOCK"


@dataclass(frozen=True)
class InvestorProfile:
    capital: float
    base_currency: str
    risk_tolerance: str
    horizon: str
    allowed_countries: tuple[str, ...] = ()
    allowed_exchanges: tuple[str, ...] = ()
    max_position_pct: float = 10.0
    max_country_pct: float = 40.0
    max_sector_pct: float = 30.0
    min_cash_reserve_pct: float = 10.0
    max_positions: int = 10
    objectives: tuple[str, ...] = ()
    liquidity_need: str = "medium"
    max_drawdown_comfort_pct: Optional[float] = None


@dataclass(frozen=True)
class PortfolioAllocation:
    identity: str
    ticker: str
    country: str
    exchange: str
    currency: str
    weight_pct: float
    amount_base_currency: float
    quantity: Optional[int]
    estimated_price: Optional[float]
    score: float
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class PortfolioProposal:
    status: str
    generated_at: str
    invested_pct: float
    cash_pct: float
    allocations: tuple[PortfolioAllocation, ...]
    excluded: tuple[str, ...] = ()
    reasoning: str = ""
