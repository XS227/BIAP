"""Provider contracts and registry for BIAP Global.

Concrete providers may wrap exchange feeds, market-data vendors, regulatory
filing systems, issuer feeds or internal relays. They must return normalized
GlobalCompany records and preserve source provenance.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
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
        enriched = self.market(company.country, company.exchange).enrich_market(company)
        return self.fundamentals(company.country, company.exchange).enrich_fundamentals(enriched)


def append_source(company: GlobalCompany, source: SourceEvidence) -> GlobalCompany:
    """Return a dataclass copy with one immutable provenance record appended."""
    return replace(company, sources=[*company.sources, source])
