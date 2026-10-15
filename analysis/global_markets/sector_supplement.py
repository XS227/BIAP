"""Fill a missing sector from the SEC SIC code of the identity-verified filer.

ESEF/OAM packages carry no sector. Issuers that also file with the SEC as
foreign private issuers (Shell, BP, ...) have an SEC registrant SIC code. It
is used *only* to fill an empty ``sector``/``industry``, only after the strict
legal-name identity check, and is labelled ``sec-sic`` (a registrant
classification, not GICS/ICB). Everything else in the result is untouched, so
no financial figure can be mixed in from another source, period or currency.
"""
from __future__ import annotations

from dataclasses import replace
import threading
import time

from .models import GlobalCompany
from .providers import FundamentalsProvider
from .sec_foreign_ifrs import SECForeignIFRSFundamentalsProvider

_NEGATIVE_TTL_SEC = 6 * 3600


class SECSectorSupplementProvider(FundamentalsProvider):
    def __init__(self, inner: FundamentalsProvider, sec: SECForeignIFRSFundamentalsProvider) -> None:
        self.inner = inner
        self.sec = sec
        self.provider_id = inner.provider_id
        self._lock = threading.Lock()
        self._negative: dict[tuple, float] = {}

    def __getattr__(self, name):  # delegate optional hooks (e.g. upstream_id)
        return getattr(self.inner, name)

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        result = self.inner.enrich_fundamentals(company)
        if result.sector:
            return result
        key = (result.country, result.exchange, result.ticker)
        now = time.monotonic()
        with self._lock:
            if self._negative.get(key, 0.0) > now:
                return result
        try:
            found = self.sec.sic_sector(result)
        except Exception:  # supplement is best-effort; never fail the analysis
            found = None
        if not found:
            with self._lock:
                self._negative[key] = now + _NEGATIVE_TTL_SEC
            return result
        return replace(
            result,
            sector=found["sector"],
            industry=result.industry or found["industry"],
            raw_provider_fields={
                **result.raw_provider_fields,
                "sector_source": "sec-sic",
                "sec_sic": found["sic"],
                "sec_cik": result.raw_provider_fields.get("sec_cik") or found["cik"],
                "sector_provenance": {
                    "classification": "SEC SIC registrant code (not GICS/ICB)",
                    "sourceUrl": found["sourceUrl"],
                    "matchedEntity": found["entityName"],
                    "identityCheck": "exact legal-name core match",
                },
            },
        )
