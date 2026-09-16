"""Persistent market-data cache for BIAP Global.

This layer never invents prices. A successful upstream market enrichment is
atomically snapshotted on the Global server. Fresh snapshots reduce provider
load; if the upstream feed is temporarily unavailable, the latest verified
snapshot can be returned with explicit fallback provenance. EvidenceAgent still
uses the original price_observed_at timestamp and will WARN/BLOCK stale data.

The provider also supports cache-only mode. That allows a deployment to keep
using previously verified snapshots even when the upstream credential is
temporarily unavailable. No snapshot means no market data; there is no synthetic
fallback.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, MarketDataProvider


_MARKET_FIELDS = (
    "currency", "mic_code", "instrument_type", "sector", "industry",
    "price", "price_observed_at", "volume_today", "avg_volume_30d",
    "market_cap", "shares_outstanding", "price_52w_high", "price_52w_low",
    "volatility_annualized_pct", "max_drawdown_pct", "return_1m_pct",
    "return_3m_pct", "return_6m_pct", "beta", "pe", "sector_pe", "pb",
    "ev_ebitda", "dividend_yield_pct", "eps", "book_value_per_share",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class PersistentMarketProvider(MarketDataProvider):
    """Wrap a verified market provider with per-instrument disk snapshots.

    ``upstream=None`` creates a read-only cache provider. That mode is useful
    during a provider outage or while credentials are being rotated.
    """

    provider_id = "persistent-market-cache"

    def __init__(
        self,
        upstream: Optional[MarketDataProvider] = None,
        *,
        data_dir: Optional[str] = None,
        fresh_hours: Optional[float] = None,
    ) -> None:
        self.upstream = upstream
        self.upstream_id = upstream.provider_id if upstream is not None else "cache-only"
        self.provider_id = f"cached:{self.upstream_id}"
        root = data_dir or os.environ.get("BIAP_GLOBAL_DATA_DIR") or "/var/lib/biap-global"
        self.root = Path(root).expanduser().resolve() / "market"
        ttl = fresh_hours if fresh_hours is not None else float(os.environ.get("BIAP_GLOBAL_MARKET_CACHE_HOURS", "6"))
        self.fresh_seconds = max(0.0, ttl * 3600.0)

    @staticmethod
    def _key(company: GlobalCompany) -> str:
        raw = f"{company.country.upper()}:{company.exchange.upper()}:{(company.mic_code or '').upper()}:{company.ticker.upper()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _slug(value: str) -> str:
        return "".join(ch for ch in value.upper() if ch.isalnum() or ch in {"-", "_"}) or "UNKNOWN"

    def _directory(self, country: str, exchange: str) -> Path:
        return self.root / self._slug(country) / self._slug(exchange)

    def _path(self, company: GlobalCompany) -> Path:
        return self._directory(company.country, company.exchange) / f"{self._key(company)}.json"

    def _read(self, company: GlobalCompany) -> Optional[dict]:
        path = self._path(company)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
            return None
        identity = payload.get("identity") or {}
        if str(identity.get("country") or "").upper() != company.country.upper():
            return None
        if str(identity.get("exchange") or "").upper() != company.exchange.upper():
            return None
        if str(identity.get("ticker") or "").upper() != company.ticker.upper():
            return None
        return payload

    @staticmethod
    def _age_seconds(payload: dict) -> Optional[float]:
        fetched = _parse_iso(payload.get("fetchedAt"))
        return None if fetched is None else max(0.0, (_utc_now() - fetched).total_seconds())

    def _is_fresh(self, payload: dict) -> bool:
        age = self._age_seconds(payload)
        return age is not None and age <= self.fresh_seconds

    def _write(self, company: GlobalCompany) -> None:
        if self.upstream is None:
            raise GlobalProviderError("cache-only market provider cannot create snapshots")
        if company.price is None or company.price <= 0 or not company.price_observed_at:
            raise GlobalProviderError("refusing to cache market snapshot without verified price and timestamp")
        path = self._path(company)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "identity": {
                "country": company.country,
                "exchange": company.exchange,
                "mic_code": company.mic_code,
                "ticker": company.ticker,
            },
            "provider": self.upstream_id,
            "fetchedAt": _utc_now().isoformat(),
            "market": {field: getattr(company, field) for field in _MARKET_FIELDS},
            "raw_provider_fields": company.raw_provider_fields,
            "sources": [asdict(source) for source in company.sources if any(token in source.source_type.lower() for token in ("market", "price", "quote", "history", "valuation", "profile"))],
        }
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temp, path)

    def _decode(self, seed: GlobalCompany, payload: dict, *, fallback: bool) -> GlobalCompany:
        market = payload.get("market") if isinstance(payload.get("market"), dict) else {}
        updates = {field: market.get(field) for field in _MARKET_FIELDS if field in market}
        stored_sources: list[SourceEvidence] = []
        for raw in payload.get("sources") or []:
            if not isinstance(raw, dict):
                continue
            try:
                stored_sources.append(SourceEvidence(**{key: raw.get(key) for key in SourceEvidence.__dataclass_fields__}))
            except TypeError:
                continue
        age = self._age_seconds(payload)
        age_hours = None if age is None else age / 3600.0
        fetched_at = str(payload.get("fetchedAt") or "") or None
        upstream = str(payload.get("provider") or self.upstream_id)
        cache_source = SourceEvidence(
            provider=self.provider_id,
            source_type="daily_market_history_cache",
            source_id=seed.identity(),
            observed_at=fetched_at,
            quality=0.78 if fallback else 0.88,
            notes=(
                f"Persistent fallback snapshot from {upstream}; cache_age_hours={age_hours:.1f}"
                if fallback and age_hours is not None
                else f"Persistent market snapshot from {upstream}"
            ),
        )
        raw_fields = dict(seed.raw_provider_fields)
        raw_fields.update(payload.get("raw_provider_fields") or {})
        raw_fields.update({
            "market_cache": "fallback" if fallback else "fresh",
            "market_cached_at": fetched_at,
            "market_cache_age_hours": None if age_hours is None else round(age_hours, 2),
            "market_upstream_provider": upstream,
        })
        return replace(
            seed,
            **updates,
            raw_provider_fields=raw_fields,
            sources=[*seed.sources, *stored_sources, cache_source],
        )

    def snapshot_info(self, company: GlobalCompany) -> dict:
        payload = self._read(company)
        if payload is None:
            return {"available": False, "provider": self.upstream_id}
        age = self._age_seconds(payload)
        market = payload.get("market") if isinstance(payload.get("market"), dict) else {}
        return {
            "available": True,
            "provider": str(payload.get("provider") or self.upstream_id),
            "fetchedAt": payload.get("fetchedAt"),
            "priceObservedAt": market.get("price_observed_at"),
            "ageHours": None if age is None else round(age / 3600.0, 2),
            "fresh": self._is_fresh(payload),
        }

    def cached_companies(self, *, country: str, exchange: str) -> list[GlobalCompany]:
        """Enumerate valid cached market snapshots for a bounded exchange scan."""
        directory = self._directory(country, exchange)
        try:
            paths = sorted(directory.glob("*.json"))
        except OSError:
            return []
        rows: list[GlobalCompany] = []
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
                continue
            identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
            if str(identity.get("country") or "").upper() != country.upper():
                continue
            if str(identity.get("exchange") or "").upper() != exchange.upper():
                continue
            market = payload.get("market") if isinstance(payload.get("market"), dict) else {}
            ticker = str(identity.get("ticker") or "").strip()
            currency = str(market.get("currency") or "").strip().upper()
            if not ticker or not currency:
                continue
            seed = GlobalCompany(
                country=country.upper(),
                exchange=exchange.upper(),
                mic_code=str(identity.get("mic_code") or "").strip().upper() or None,
                currency=currency,
                ticker=ticker,
                name=ticker,
            )
            rows.append(self._decode(seed, payload, fallback=True))
        return rows

    def refresh(self, company: GlobalCompany) -> GlobalCompany:
        if self.upstream is None:
            raise GlobalProviderError("market upstream is not configured; cache-only mode")
        enriched = self.upstream.enrich_market(company)
        self._write(enriched)
        payload = self._read(company)
        return self._decode(company, payload, fallback=False) if payload else enriched

    def enrich_market(self, company: GlobalCompany) -> GlobalCompany:
        cached = self._read(company)
        if cached is not None and self._is_fresh(cached):
            return self._decode(company, cached, fallback=False)
        if self.upstream is None:
            if cached is not None:
                return self._decode(company, cached, fallback=True)
            raise GlobalProviderError("market upstream is not configured and no verified cache exists")
        try:
            return self.refresh(company)
        except Exception as exc:
            if cached is not None:
                return self._decode(company, cached, fallback=True)
            if isinstance(exc, GlobalProviderError):
                raise
            raise GlobalProviderError(f"market data unavailable and no cache exists: {type(exc).__name__}") from exc
