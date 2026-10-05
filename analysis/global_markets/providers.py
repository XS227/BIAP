"""Provider contracts and registry for BIAP Global.

Concrete providers may wrap exchange feeds, market-data vendors, regulatory
filing systems, issuer feeds or internal relays. They must return normalized
GlobalCompany records and preserve source provenance. Provider failures are
isolated: missing data lowers evidence quality instead of fabricating values or
unnecessarily discarding data returned by another healthy source.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Iterable, Optional

from .models import GlobalCompany, SourceEvidence


class GlobalProviderError(RuntimeError):
    """Raised when a provider cannot return verified normalized data."""


class InstrumentUniverseProvider(ABC):
    provider_id: str

    @abstractmethod
    def list_instruments(
        self,
        *,
        country: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> Iterable[GlobalCompany]:
        """Return instrument identities; financial fields may be empty."""


class MarketDataProvider(ABC):
    provider_id: str

    @abstractmethod
    def enrich_market(self, company: GlobalCompany) -> GlobalCompany:
        """Return a copy enriched with verified market/valuation data."""


class FundamentalsProvider(ABC):
    provider_id: str

    @abstractmethod
    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        """Return a copy enriched with verified filings/fundamentals."""


@dataclass(frozen=True)
class ProviderDiagnostics:
    market_status: str
    fundamentals_status: str
    market_provider: Optional[str] = None
    fundamentals_provider: Optional[str] = None
    market_error: Optional[str] = None
    fundamentals_error: Optional[str] = None

    @property
    def degraded(self) -> bool:
        return self.market_status != "ok" or self.fundamentals_status != "ok"

    def to_dict(self) -> dict:
        return {
            "marketStatus": self.market_status,
            "fundamentalsStatus": self.fundamentals_status,
            "marketProvider": self.market_provider,
            "fundamentalsProvider": self.fundamentals_provider,
            "marketError": self.market_error,
            "fundamentalsError": self.fundamentals_error,
            "degraded": self.degraded,
        }


class ProviderRegistry:
    """Maps country/exchange keys to provider implementations.

    The registry keeps provider selection outside agent logic. A deployment can
    replace one upstream source without changing the normalized global agents.
    """

    def __init__(self) -> None:
        self._universe: dict[tuple[str, str], InstrumentUniverseProvider] = {}
        self._market: dict[tuple[str, str], MarketDataProvider] = {}
        self._fundamentals: dict[tuple[str, str], FundamentalsProvider] = {}

    @staticmethod
    def _key(country: str, exchange: str) -> tuple[str, str]:
        return country.strip().upper(), exchange.strip().upper()

    def register_universe(self, country: str, exchange: str, provider: InstrumentUniverseProvider) -> None:
        self._universe[self._key(country, exchange)] = provider

    def register_market(self, country: str, exchange: str, provider: MarketDataProvider) -> None:
        self._market[self._key(country, exchange)] = provider

    def register_fundamentals(self, country: str, exchange: str, provider: FundamentalsProvider) -> None:
        self._fundamentals[self._key(country, exchange)] = provider

    def universe(self, country: str, exchange: str) -> InstrumentUniverseProvider:
        try:
            return self._universe[self._key(country, exchange)]
        except KeyError as exc:
            raise GlobalProviderError(f"no universe provider for {country}/{exchange}") from exc

    def market(self, country: str, exchange: str) -> MarketDataProvider:
        try:
            return self._market[self._key(country, exchange)]
        except KeyError as exc:
            raise GlobalProviderError(f"no market provider for {country}/{exchange}") from exc

    def fundamentals(self, country: str, exchange: str) -> FundamentalsProvider:
        try:
            return self._fundamentals[self._key(country, exchange)]
        except KeyError as exc:
            raise GlobalProviderError(f"no fundamentals provider for {country}/{exchange}") from exc

    def enrich(self, company: GlobalCompany) -> GlobalCompany:
        """Strict enrichment: both registered providers must succeed."""
        enriched = self.market(company.country, company.exchange).enrich_market(company)
        return self.fundamentals(company.country, company.exchange).enrich_fundamentals(enriched)

    def enrich_best_effort(self, company: GlobalCompany) -> tuple[GlobalCompany, ProviderDiagnostics]:
        """Keep healthy evidence when one provider is absent or temporarily fails.

        This method never converts a provider failure into synthetic values. The
        Evidence Agent sees the actual missing fields/provenance and can WARN or
        BLOCK the final recommendation.
        """
        enriched = company
        market_status = "unconfigured"
        fundamentals_status = "unconfigured"
        market_provider_id = None
        fundamentals_provider_id = None
        market_error = None
        fundamentals_error = None

        try:
            market_provider = self.market(company.country, company.exchange)
            market_provider_id = market_provider.provider_id
            enriched = market_provider.enrich_market(enriched)
            market_status = "ok"
        except Exception as exc:
            market_status = "error" if market_provider_id else "unconfigured"
            market_error = str(exc)[:300]

        try:
            fundamentals_provider = self.fundamentals(company.country, company.exchange)
            fundamentals_provider_id = fundamentals_provider.provider_id
            enriched = fundamentals_provider.enrich_fundamentals(enriched)
            fundamentals_status = "ok"
        except Exception as exc:
            fundamentals_status = "error" if fundamentals_provider_id else "unconfigured"
            fundamentals_error = str(exc)[:300]

        return enriched, ProviderDiagnostics(
            market_status=market_status,
            fundamentals_status=fundamentals_status,
            market_provider=market_provider_id,
            fundamentals_provider=fundamentals_provider_id,
            market_error=market_error,
            fundamentals_error=fundamentals_error,
        )


def append_source(company: GlobalCompany, source: SourceEvidence) -> GlobalCompany:
    """Return a dataclass copy with one immutable provenance record appended."""
    return replace(company, sources=[*company.sources, source])
