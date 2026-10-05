"""Compose fundamentals with independent official corroboration sources.

Corroborators may add legal-entity, registry, audit or filing metadata, but they
must not fabricate fundamentals. A corroborator failure is isolated and recorded
in raw_provider_fields so a healthy financial-statement source is preserved.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .models import GlobalCompany
from .providers import FundamentalsProvider, GlobalProviderError


class EvidenceCorroborator(Protocol):
    provider_id: str

    def corroborate(self, company: GlobalCompany) -> GlobalCompany:
        ...


class CorroboratingFundamentalsProvider(FundamentalsProvider):
    def __init__(self, base: FundamentalsProvider, *corroborators: EvidenceCorroborator) -> None:
        self.base = base
        self.corroborators = tuple(corroborators)
        suffix = "+".join(item.provider_id for item in self.corroborators)
        self.provider_id = base.provider_id if not suffix else f"{base.provider_id}+corroborated:{suffix}"

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        enriched = self.base.enrich_fundamentals(company)
        errors: dict[str, str] = {}
        for corroborator in self.corroborators:
            try:
                enriched = corroborator.corroborate(enriched)
            except GlobalProviderError as exc:
                errors[corroborator.provider_id] = str(exc)[:240]
            except Exception as exc:  # keep one optional corroborator from breaking analysis
                errors[corroborator.provider_id] = f"{type(exc).__name__}: {str(exc)[:180]}"
        if errors:
            enriched = replace(
                enriched,
                raw_provider_fields={
                    **enriched.raw_provider_fields,
                    "corroboration_errors": errors,
                },
            )
        return enriched
