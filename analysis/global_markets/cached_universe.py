"""Persistent instrument-universe cache for BIAP Global.

The cache is a resilience layer, not a source of truth. A successful upstream
catalog request is normalized and atomically snapshotted under
BIAP_GLOBAL_DATA_DIR. If the upstream catalog is temporarily unavailable, BIAP
can serve the latest verified snapshot while preserving its age/provenance.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Iterable, Optional

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider
from .country_packs import get_exchange
from .universe import _ordinary_equity_row

# Version 18 replaces the Switzerland reference/demo catalog with the official
# SIX Swiss primary ordinary-share universe. Older Swiss snapshots must not
# survive the authoritative source change.
CACHE_SCHEMA_VERSION = 18


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class PersistentUniverseProvider(InstrumentUniverseProvider):
    """Wrap an upstream universe provider with an atomic disk snapshot.

    Fresh cache entries are served immediately to avoid repeatedly downloading
    large exchange catalogs. Once the freshness TTL expires, the next request
    refreshes upstream. On upstream failure, the latest cached snapshot is used
    regardless of age, and the cached SourceEvidence makes that fallback
    explicit to downstream diagnostics.
    """

    provider_id = "persistent-universe-cache"

    def __init__(
        self,
        upstream: InstrumentUniverseProvider,
        *,
        data_dir: Optional[str] = None,
        fresh_hours: Optional[float] = None,
    ) -> None:
        self.upstream = upstream
        self.provider_id = f"cached:{upstream.provider_id}"
        root = data_dir or os.environ.get("BIAP_GLOBAL_DATA_DIR") or "/var/lib/biap-global"
        self.root = Path(root).expanduser().resolve() / "universe"
        ttl = fresh_hours if fresh_hours is not None else float(os.environ.get("BIAP_GLOBAL_UNIVERSE_CACHE_HOURS", "12"))
        self.fresh_seconds = max(0.0, ttl * 3600.0)

    @staticmethod
    def _slug(value: str) -> str:
        return "".join(ch for ch in value.upper() if ch.isalnum() or ch in {"-", "_"}) or "UNKNOWN"

    def _path(self, country: str, exchange: str) -> Path:
        return self.root / self._slug(country) / f"{self._slug(exchange)}.json"

    def _read_payload(self, country: str, exchange: str) -> Optional[dict]:
        path = self._path(country, exchange)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(payload, dict) or payload.get("schemaVersion") != CACHE_SCHEMA_VERSION:
            return None
        if str(payload.get("country") or "").upper() != country.upper():
            return None
        if str(payload.get("exchange") or "").upper() != exchange.upper():
            return None
        expected_provider = str(getattr(self.upstream, "provider_id", "") or "")
        cached_provider = str(payload.get("provider") or "")
        if expected_provider and cached_provider != expected_provider:
            return None
        if not isinstance(payload.get("instruments"), list):
            return None
        return payload

    def _age_seconds(self, payload: dict) -> Optional[float]:
        fetched = _parse_iso(payload.get("fetchedAt"))
        if fetched is None:
            return None
        return max(0.0, (_utc_now() - fetched).total_seconds())

    def _is_fresh(self, payload: dict) -> bool:
        age = self._age_seconds(payload)
        return age is not None and age <= self.fresh_seconds

    @staticmethod
    def _row(company: GlobalCompany) -> dict:
        return {
            "country": company.country,
            "exchange": company.exchange,
            "currency": company.currency,
            "ticker": company.ticker,
            "name": company.name,
            "mic_code": company.mic_code,
            "isin": company.isin,
            "lei": company.lei,
            "instrument_type": company.instrument_type,
            "sector": company.sector,
            "industry": company.industry,
            "lot_size": company.lot_size,
            "raw_provider_fields": company.raw_provider_fields,
            "sources": [asdict(source) for source in company.sources],
        }

    def _write(self, country: str, exchange: str, rows: list[GlobalCompany]) -> None:
        if not rows:
            raise GlobalProviderError("refusing to replace universe cache with an empty snapshot")
        path = self._path(country, exchange)
        path.parent.mkdir(parents=True, exist_ok=True)
        now = _utc_now().isoformat()
        upstream_metadata = getattr(self.upstream, "last_metadata", {})
        metadata = dict(upstream_metadata) if isinstance(upstream_metadata, dict) else {}
        try:
            official_count = max(len(rows), int(metadata.get("officialCount") or len(rows)))
        except (TypeError, ValueError):
            official_count = len(rows)
        metadata["officialCount"] = official_count
        metadata["resolvedCount"] = len(rows)
        metadata["resolutionCoveragePct"] = round(100.0 * len(rows) / official_count, 2) if official_count else 0.0
        payload = {
            "schemaVersion": CACHE_SCHEMA_VERSION,
            "country": country.upper(),
            "exchange": exchange.upper(),
            "provider": self.upstream.provider_id,
            "fetchedAt": now,
            "count": len(rows),
            "metadata": metadata,
            "instruments": [self._row(row) for row in rows],
        }
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, path)

    def _decode(self, payload: dict, *, fallback: bool) -> list[GlobalCompany]:
        fetched_at = str(payload.get("fetchedAt") or "") or None
        upstream = str(payload.get("provider") or "unknown")
        age = self._age_seconds(payload)
        age_hours = None if age is None else age / 3600.0
        result: list[GlobalCompany] = []
        for row in payload.get("instruments") or []:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "").strip()
            currency = str(row.get("currency") or "").strip().upper()
            if not ticker or not currency:
                continue
            row_country = str(row.get("country") or "").upper()
            row_exchange = str(row.get("exchange") or "").upper()
            try:
                spec = get_exchange(row_country, row_exchange)
            except Exception:
                continue
            cached_raw = dict(row.get("raw_provider_fields") or {})
            normalized_row = {
                "name": str(row.get("name") or ticker),
                "type": str(row.get("instrument_type") or "Common Stock"),
                "cfi_code": cached_raw.get("cfi"),
                "trusted_official_equity": cached_raw.get("trusted_official_equity") is True,
            }
            if not _ordinary_equity_row(
                country=row_country,
                spec=spec,
                row=normalized_row,
                symbol=ticker,
                currency=currency,
            ):
                continue
            # Cached venue membership must be just as strict as live discovery.
            # A configured exchange is not trusted unless its cached MIC proves
            # membership in that venue's accepted MIC set.
            cached_mic = str(row.get("mic_code") or "").strip().upper()
            accepted_mics = set(spec.accepted_mics)
            if accepted_mics and (not cached_mic or cached_mic not in accepted_mics):
                continue
            original_sources: list[SourceEvidence] = []
            for source in row.get("sources") or []:
                if not isinstance(source, dict):
                    continue
                try:
                    original_sources.append(SourceEvidence(**{key: source.get(key) for key in SourceEvidence.__dataclass_fields__}))
                except TypeError:
                    continue
            cache_source = SourceEvidence(
                provider=self.provider_id,
                source_type="instrument_reference_cache",
                source_id=f"{str(row.get('country') or '').upper()}:{str(row.get('exchange') or '').upper()}:{ticker}",
                observed_at=fetched_at,
                quality=0.82 if fallback else 0.88,
                notes=(
                    f"Persistent fallback snapshot from {upstream}; age_hours={age_hours:.1f}"
                    if fallback and age_hours is not None
                    else f"Persistent snapshot from {upstream}"
                ),
            )
            raw = cached_raw
            raw.update({
                "catalog_cache": "fallback" if fallback else "fresh",
                "catalog_cached_at": fetched_at,
                "catalog_upstream_provider": upstream,
                "catalog_age_hours": None if age_hours is None else round(age_hours, 2),
            })
            result.append(GlobalCompany(
                country=str(row.get("country") or "").upper(),
                exchange=str(row.get("exchange") or "").upper(),
                currency=currency,
                ticker=ticker,
                name=str(row.get("name") or ticker).strip(),
                mic_code=str(row.get("mic_code") or "").strip().upper() or None,
                isin=str(row.get("isin") or "").strip().upper() or None,
                lei=str(row.get("lei") or "").strip().upper() or None,
                instrument_type=str(row.get("instrument_type") or "Common Stock"),
                sector=str(row.get("sector") or "").strip() or None,
                industry=str(row.get("industry") or "").strip() or None,
                lot_size=row.get("lot_size") if isinstance(row.get("lot_size"), int) else None,
                raw_provider_fields=raw,
                sources=[*original_sources, cache_source],
            ))
        return result

    def snapshot_info(self, *, country: str, exchange: str) -> dict:
        payload = self._read_payload(country, exchange)
        if payload is None:
            return {"available": False, "provider": self.upstream.provider_id}
        age = self._age_seconds(payload)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        count = int(payload.get("count") or 0)
        try:
            official_count = max(count, int(metadata.get("officialCount") or count))
        except (TypeError, ValueError):
            official_count = count
        try:
            resolved_count = int(metadata.get("resolvedCount") or count)
        except (TypeError, ValueError):
            resolved_count = count
        coverage = round(100.0 * resolved_count / official_count, 2) if official_count else 0.0
        return {
            "available": True,
            "provider": str(payload.get("provider") or self.upstream.provider_id),
            "fetchedAt": payload.get("fetchedAt"),
            "count": count,
            "officialCount": official_count,
            "resolvedCount": resolved_count,
            "resolutionCoveragePct": coverage,
            "metadata": metadata,
            "ageHours": None if age is None else round(age / 3600.0, 2),
            "fresh": self._is_fresh(payload),
            "schemaVersion": CACHE_SCHEMA_VERSION,
        }

    def refresh(self, *, country: str, exchange: str) -> list[GlobalCompany]:
        rows = list(self.upstream.list_instruments(country=country, exchange=exchange))
        self._write(country, exchange, rows)
        payload = self._read_payload(country, exchange)
        return self._decode(payload, fallback=False) if payload else rows

    def search_instruments(
        self,
        *,
        country: str,
        exchange: str,
        query: str,
        limit: int = 120,
    ) -> list[GlobalCompany]:
        """Forward targeted discovery to the upstream provider when supported.

        This path deliberately does not replace the exchange snapshot. It is a
        targeted recovery path for symbols/names that are not present in an old
        or incomplete local catalog.
        """
        search = getattr(self.upstream, "search_instruments", None)
        if not callable(search):
            return []
        try:
            return list(search(country=country, exchange=exchange, query=query, limit=limit))
        except GlobalProviderError:
            return []

    def list_instruments(
        self,
        *,
        country: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> Iterable[GlobalCompany]:
        if not country or not exchange:
            raise GlobalProviderError("country and exchange are required for cached instrument discovery")
        cached = self._read_payload(country, exchange)
        if cached is not None and self._is_fresh(cached):
            return self._decode(cached, fallback=False)
        try:
            return self.refresh(country=country, exchange=exchange)
        except Exception as exc:
            if cached is not None:
                return self._decode(cached, fallback=True)
            if isinstance(exc, GlobalProviderError):
                raise
            raise GlobalProviderError(f"instrument catalog unavailable and no cache exists: {type(exc).__name__}") from exc
