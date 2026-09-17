"""Persistent fundamentals snapshots for BIAP Global.

Official/regulatory fundamentals change far less often than market prices. This
wrapper stores every successful normalized filing snapshot outside the Git
checkout so BIAP can keep using the last verified filing during a temporary
source outage. Snapshots are immutable by filing period as well as mirrored to a
``latest`` file for fast reads.

The wrapper never upgrades vendor data to official evidence: original
``SourceEvidence`` records are restored exactly, and the cache marker itself is
plain cache provenance. EvidenceAgent therefore still blocks a snapshot whose
only underlying source is a public vendor fallback.
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
from .providers import FundamentalsProvider, GlobalProviderError, append_source


_FUNDAMENTAL_FIELDS = (
    "name", "lei", "sector", "industry", "reporting_currency",
    "shares_outstanding", "eps", "book_value_per_share",
    "revenue", "revenue_prev", "revenue_yoy_pct", "gross_profit",
    "operating_income", "ebitda", "net_income", "net_margin_pct",
    "net_margin_prev_pct", "total_assets", "total_liabilities",
    "total_equity", "current_assets", "current_liabilities",
    "cash_and_equivalents", "operating_cash_flow", "free_cash_flow",
    "total_debt", "interest_expense", "audit_opinion",
    "filing_period_end", "filing_observed_at", "report_scope",
    "restatement_flag", "material_event_flags",
)

_OFFICIAL_SOURCE_TOKENS = ("official", "regulatory", "xbrl", "filing")


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


def _official_sources(company: GlobalCompany) -> list[SourceEvidence]:
    rows: list[SourceEvidence] = []
    for source in company.sources:
        kind = source.source_type.lower().replace("-", "_")
        provider = source.provider.lower()
        if "vendor" in kind or "vendor" in provider:
            continue
        if any(token in kind for token in _OFFICIAL_SOURCE_TOKENS):
            rows.append(source)
    return rows


class PersistentFundamentalsProvider(FundamentalsProvider):
    """Disk-backed wrapper around a fundamentals provider.

    Fresh *official* cache entries can satisfy a request without re-querying a
    regulator. Non-official vendor fallback snapshots are retained for display
    resilience but never suppress a retry of the official upstream.
    """

    provider_id = "persistent-fundamentals-cache"

    def __init__(
        self,
        upstream: FundamentalsProvider,
        *,
        data_dir: Optional[str] = None,
        fresh_hours: Optional[float] = None,
    ) -> None:
        self.upstream = upstream
        self.upstream_id = upstream.provider_id
        self.provider_id = f"cached:{self.upstream_id}"
        root = data_dir or os.environ.get("BIAP_GLOBAL_DATA_DIR") or "/var/lib/biap-global"
        self.root = Path(root).expanduser().resolve() / "fundamentals"
        ttl = fresh_hours if fresh_hours is not None else float(os.environ.get("BIAP_GLOBAL_FUNDAMENTALS_CACHE_HOURS", "24"))
        self.fresh_seconds = max(0.0, ttl * 3600.0)

    @staticmethod
    def _slug(value: str) -> str:
        return "".join(ch for ch in value.upper() if ch.isalnum() or ch in {"-", "_"}) or "UNKNOWN"

    @staticmethod
    def _key(company: GlobalCompany) -> str:
        raw = f"{company.country.upper()}:{company.exchange.upper()}:{company.ticker.upper()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    def _directory(self, company: GlobalCompany) -> Path:
        return self.root / self._slug(company.country) / self._slug(company.exchange) / f"{self._slug(company.ticker)}-{self._key(company)}"

    def _latest_path(self, company: GlobalCompany) -> Path:
        return self._directory(company) / "latest.json"

    def _archive_path(self, company: GlobalCompany, period_end: Optional[str]) -> Path:
        period = self._slug(period_end or "UNDATED")
        return self._directory(company) / "history" / f"{period}.json"

    def _read(self, company: GlobalCompany) -> Optional[dict]:
        try:
            payload = json.loads(self._latest_path(company).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
            return None
        identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
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
        sources = [asdict(source) for source in company.sources]
        official = bool(_official_sources(company))
        payload = {
            "schemaVersion": 1,
            "identity": {
                "country": company.country,
                "exchange": company.exchange,
                "mic_code": company.mic_code,
                "ticker": company.ticker,
                "isin": company.isin,
            },
            "provider": self.upstream_id,
            "fetchedAt": _utc_now().isoformat(),
            "officialEvidence": official,
            "filingPeriodEnd": company.filing_period_end,
            "fundamentals": {field: getattr(company, field) for field in _FUNDAMENTAL_FIELDS},
            "raw_provider_fields": company.raw_provider_fields,
            "sources": sources,
        }
        directory = self._directory(company)
        directory.mkdir(parents=True, exist_ok=True)
        latest = self._latest_path(company)
        temp = latest.with_suffix(".json.tmp")
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, latest)

        archive = self._archive_path(company, company.filing_period_end)
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.exists() or official:
            archive_tmp = archive.with_suffix(".json.tmp")
            archive_tmp.write_text(text, encoding="utf-8")
            os.replace(archive_tmp, archive)

    def _decode(self, seed: GlobalCompany, payload: dict, *, fallback: bool) -> GlobalCompany:
        stored = payload.get("fundamentals") if isinstance(payload.get("fundamentals"), dict) else {}
        updates = {}
        for field in _FUNDAMENTAL_FIELDS:
            if field not in stored:
                continue
            value = stored.get(field)
            if field == "material_event_flags" and isinstance(value, list):
                value = tuple(str(item) for item in value)
            if value is not None:
                updates[field] = value

        restored_sources: list[SourceEvidence] = []
        for raw in payload.get("sources") or []:
            if not isinstance(raw, dict):
                continue
            try:
                restored_sources.append(SourceEvidence(**{key: raw.get(key) for key in SourceEvidence.__dataclass_fields__}))
            except TypeError:
                continue

        raw_fields = dict(seed.raw_provider_fields)
        raw_fields.update(payload.get("raw_provider_fields") or {})
        age = self._age_seconds(payload)
        raw_fields.update({
            "fundamentals_cache": "fallback" if fallback else "fresh",
            "fundamentals_cached_at": payload.get("fetchedAt"),
            "fundamentals_cache_age_hours": None if age is None else round(age / 3600.0, 2),
            "fundamentals_upstream_provider": payload.get("provider") or self.upstream_id,
            "fundamentals_cached_official": bool(payload.get("officialEvidence")),
        })
        enriched = replace(seed, **updates, raw_provider_fields=raw_fields, sources=[*seed.sources, *restored_sources])
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="cache_snapshot",
            source_id=enriched.identity(),
            observed_at=str(payload.get("fetchedAt") or "") or None,
            period_end=enriched.filing_period_end,
            quality=0.82 if fallback else 0.90,
            notes="Persistent normalized fundamentals snapshot; underlying source provenance is preserved unchanged.",
        ))

    def snapshot_info(self, company: GlobalCompany) -> dict:
        payload = self._read(company)
        if payload is None:
            return {"available": False, "provider": self.upstream_id}
        age = self._age_seconds(payload)
        return {
            "available": True,
            "provider": payload.get("provider") or self.upstream_id,
            "fetchedAt": payload.get("fetchedAt"),
            "filingPeriodEnd": payload.get("filingPeriodEnd"),
            "officialEvidence": bool(payload.get("officialEvidence")),
            "ageHours": None if age is None else round(age / 3600.0, 2),
            "fresh": self._is_fresh(payload),
        }

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        cached = self._read(company)
        if cached is not None and bool(cached.get("officialEvidence")) and self._is_fresh(cached):
            return self._decode(company, cached, fallback=False)
        try:
            enriched = self.upstream.enrich_fundamentals(company)
            self._write(enriched)
            return enriched
        except Exception as exc:
            if cached is not None:
                return self._decode(company, cached, fallback=True)
            if isinstance(exc, GlobalProviderError):
                raise
            raise GlobalProviderError(f"fundamentals unavailable and no cache exists: {type(exc).__name__}") from exc
