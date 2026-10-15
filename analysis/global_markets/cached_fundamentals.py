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
import threading
import time
from pathlib import Path
from typing import Optional

from .evidence_contract import fundamental_evidence_contract, is_official_fundamental_source, official_fundamental_sources
from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source
from .source_cache import write_bulk_text


_FUNDAMENTAL_FIELDS = (
    "name", "lei", "sector", "industry", "reporting_currency",
    "shares_outstanding", "eps", "book_value_per_share",
    "dividend_per_share", "dividend_yield_pct",
    "revenue", "revenue_prev", "revenue_yoy_pct", "gross_profit",
    "operating_income", "ebitda", "net_income", "net_margin_pct",
    "net_margin_prev_pct", "total_assets", "total_liabilities",
    "total_equity", "retained_earnings", "current_assets", "current_liabilities",
    "cash_and_equivalents", "operating_cash_flow", "free_cash_flow",
    "total_debt", "interest_expense", "audit_opinion",
    "filing_period_end", "filing_observed_at", "report_scope",
    "restatement_flag", "material_event_flags",
)

# Match EvidenceAgent's concept of a verified financial source. ``official`` by
# itself is deliberately insufficient: an official company registry may verify
# legal identity, but it is not an official financial statement.
_OFFICIAL_FINANCIAL_TOKENS = ("filing", "regulatory", "xbrl", "financial_statement")
_CACHE_SOURCE_TOKENS = (*_OFFICIAL_FINANCIAL_TOKENS, "fundamental", "financial_metrics", "company_registry")
# v3: canonical evidence contract stored with every snapshot; official flag is
# re-verified against stored source rows on read.
# v4: ESEF flows anchored to the report's period end (no prior-fiscal-year
# flows in a transition period) and bank Circular 262 revenue/equity,
# including owners/NCI statement-of-changes-in-equity columns.
# v6: refresh previously normalized snapshots after ESEF balance-sheet
# liability derivation changes; historical snapshots remain fallback evidence.
# v7: ESEF retained-earnings column, D&A/debt/capex lines and filing-derived
# FFO (Agents 9/10 inputs) after the all-facts OAM package parse.
# v8: ESEF debt includes IFRS loans-received lines next to bonds issued.
# v9: KAP income statement (Flight rows) merged with 1000TL units, SEC equity
# balance-sheet check + assessed-tax revenue tag, ESEF revenue fallbacks.
CACHE_SCHEMA_VERSION = 11
# Targeted re-normalization (instead of a global schema bump, which would force
# a re-parse of every cached issuer snapshot during live scans): revision 1 maps
# IFRS LongtermBorrowings/CurrentBorrowingsAndCurrentPortion... debt tags (Shell
# FY2025 total_debt) and adds the SEC SIC sector supplement for GB. Snapshots
# written before it are refreshed once, only when the affected field is empty.
#
# revision 2: ESEF field_status provenance, debt-component consistency guard and
# plain/issued share counts mapped by the current extractor. Official snapshots
# written earlier are re-normalized from the cached filing package (no refetch)
# once, when shares, debt or EBITDA is empty.
#
# revision 3: cross-footed ESEF extension equity (FinecoBank) and the taxonomy
# bank flag. Only official snapshots whose total_equity is still empty are
# re-normalized; snapshots that merely lack debt/EBITDA were already retried
# at revision 2 and are not re-queued (that would re-fetch thousands of issuers
# for fields the sources do not publish).
#
# revision 4: reviewed issuer D&A lines (Kitron) and the flagged non-standard
# EBITDA-incl-impairment metadata. Only official snapshots that tagged an
# impairment-inclusive D&A line as the sole D&A candidate (field_status
# ``tagged_da_impairment_inclusive_only_not_used``) are re-normalized, from the
# cached filing package.
#
# revision 5: SEC cover-page share count (dei:EntityCommonStockSharesOutstanding)
# for single-class 10-K/10-Q filers that tag no us-gaap share count. Only SEC
# snapshots whose shares_outstanding is still empty are re-normalized.
NORMALIZER_REVISION = 5

# Official providers whose records were found defective after the fact.
# Snapshots built from them are ignored (neither fresh nor stale fallback).
_REVOKED_OFFICIAL_PROVIDERS = frozenset({"unternehmensregister-de-auto"})
MAX_OFFICIAL_FILING_AGE_DAYS = int(os.environ.get("BIAP_GLOBAL_MAX_OFFICIAL_FILING_AGE_DAYS", "550"))


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
    # One definition shared with EvidenceAgent and the API contract.
    return official_fundamental_sources(company)


def _payload_official_sources(payload: dict) -> list[dict]:
    """Official rows actually present in a stored snapshot (never trusts the flag)."""
    rows = []
    for raw in payload.get("sources") or []:
        if not isinstance(raw, dict):
            continue
        try:
            source = SourceEvidence(**{key: raw.get(key) for key in SourceEvidence.__dataclass_fields__ if key in raw})
        except TypeError:
            continue
        if is_official_fundamental_source(source):
            rows.append(raw)
    return rows


def _cache_sources(company: GlobalCompany) -> list[SourceEvidence]:
    """Persist fundamentals/corroboration provenance, never market provenance."""
    rows: list[SourceEvidence] = []
    for source in company.sources:
        kind = source.source_type.lower().replace("-", "_")
        if any(token in kind for token in _CACHE_SOURCE_TOKENS):
            rows.append(source)
    return rows


class _RenormalizationBudget:
    """Spread the one-time re-normalization of old snapshots over time.

    A live scan deep-analyzes up to 75 issuers; if all of them needed a refresh
    at once the request would stall on 75 upstream fetches (and the 2 GB host
    would swap). Only a few are allowed per minute, the rest keep serving their
    valid snapshot and migrate on later requests.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stamps: list[float] = []

    def try_take(self) -> bool:
        limit = max(0, int(os.environ.get("BIAP_GLOBAL_RENORM_PER_MIN", "6")))
        now = time.monotonic()
        with self._lock:
            self._stamps = [t for t in self._stamps if now - t < 60.0]
            if len(self._stamps) >= limit:
                return False
            self._stamps.append(now)
            return True


_renormalization_budget = _RenormalizationBudget()


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
        if not isinstance(payload, dict) or payload.get("schemaVersion") not in {1, 2, 3, 4, 6, 7, 8, 9, 10, CACHE_SCHEMA_VERSION}:
            return None
        identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
        if str(identity.get("country") or "").upper() != company.country.upper():
            return None
        if str(identity.get("exchange") or "").upper() != company.exchange.upper():
            return None
        if str(identity.get("ticker") or "").upper() != company.ticker.upper():
            return None
        if any(
            isinstance(raw, dict) and str(raw.get("provider") or "").strip().lower() in _REVOKED_OFFICIAL_PROVIDERS
            for raw in payload.get("sources") or []
        ):
            return None
        # A snapshot may claim officialEvidence without carrying a verifiable
        # official source row (older writers, or metadata lost in transit).
        # Such a claim is never honoured: the record is treated as
        # non-official, so it cannot short-circuit a refresh and cannot be
        # served as official evidence.
        if payload.get("officialEvidence") and not _payload_official_sources(payload):
            payload = {**payload, "officialEvidence": False, "officialClaimRejected": True}
        return payload

    @staticmethod
    def _age_seconds(payload: dict) -> Optional[float]:
        fetched = _parse_iso(payload.get("fetchedAt"))
        return None if fetched is None else max(0.0, (_utc_now() - fetched).total_seconds())

    @staticmethod
    def _filing_age_days(payload: dict) -> Optional[float]:
        period = _parse_iso(payload.get("filingPeriodEnd"))
        return None if period is None else max(0.0, (_utc_now() - period).total_seconds() / 86400.0)

    @classmethod
    def _stale_official_filing(cls, payload: dict) -> bool:
        if not bool(payload.get("officialEvidence")):
            return False
        if not payload.get("filingPeriodEnd"):
            # An official claim with no filing period cannot be current
            # (e.g. an SEC successor CIK before its first 10-K). Börse
            # Frankfurt year-only key data is the one reviewed undated form.
            raw = payload.get("raw_provider_fields") if isinstance(payload.get("raw_provider_fields"), dict) else {}
            return raw.get("de_bf_period_granularity") != "year_only"
        age_days = cls._filing_age_days(payload)
        return age_days is not None and age_days > MAX_OFFICIAL_FILING_AGE_DAYS

    @staticmethod
    def _needs_renormalization(payload: dict) -> bool:
        if int(payload.get("normalizerRevision") or 0) >= NORMALIZER_REVISION or not payload.get("officialEvidence"):
            return False
        fundamentals = payload.get("fundamentals") if isinstance(payload.get("fundamentals"), dict) else {}
        identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
        equity_missing = fundamentals.get("total_equity") is None
        raw = payload.get("raw_provider_fields") if isinstance(payload.get("raw_provider_fields"), dict) else {}
        sec_shares_missing = raw.get("sec_cik") is not None and fundamentals.get("shares_outstanding") is None
        if int(payload.get("normalizerRevision") or 0) == 4:
            return sec_shares_missing
        if int(payload.get("normalizerRevision") or 0) >= 3:
            credit = raw.get("oam_credit_extraction") if isinstance(raw.get("oam_credit_extraction"), dict) else {}
            status = credit.get("field_status") if isinstance(credit.get("field_status"), dict) else {}
            impairment_only = (
                fundamentals.get("ebitda") is None
                and status.get("ebitda") == "tagged_da_impairment_inclusive_only_not_used"
            )
            return equity_missing or impairment_only or sec_shares_missing
        if int(payload.get("normalizerRevision") or 0) >= 2:
            return equity_missing
        gb_sector_missing = str(identity.get("country") or "").upper() == "GB" and not fundamentals.get("sector")
        inputs_missing = any(fundamentals.get(key) is None for key in ("shares_outstanding", "total_debt", "ebitda"))
        return gb_sector_missing or inputs_missing or equity_missing or sec_shares_missing

    @staticmethod
    def _superseded_by_reviewed_report(payload: dict) -> bool:
        """A year-only exchange key-data snapshot is not fresh once a reviewed
        issuer annual report exists for the same ISIN (reviewed source ranks higher)."""
        sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
        providers = {str(row.get("provider") or "") for row in sources if isinstance(row, dict)}
        if "official-boerse-frankfurt-historical-key-data" not in providers:
            return False
        if "de-reviewed-issuer-annual-report" in providers:
            return False
        identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
        isin = str(identity.get("isin") or "").upper()
        try:
            from .german_reviewed_reports import _registry

            return isin in _registry()
        except Exception:  # registry unreadable: keep prior behaviour
            return False

    def _is_fresh(self, payload: dict) -> bool:
        # Schema v2 adds shareholder-return fields such as dividend/share.
        # A v1 cache can still be used as an outage fallback, but it is never
        # considered fresh so the next normal request refreshes it once.
        if payload.get("schemaVersion") != CACHE_SCHEMA_VERSION:
            return False
        # A changed upstream/provider id can represent parser semantics or a
        # different evidence chain. Never let a previous provider snapshot
        # suppress the first refresh after such a deployment.
        if str(payload.get("provider") or "") != self.upstream_id:
            return False
        # A recently cached response can still contain an obsolete annual
        # filing. Never let cache recency turn stale official fundamentals into
        # current evidence.
        if self._stale_official_filing(payload):
            return False
        if self._superseded_by_reviewed_report(payload):
            return False
        if self._needs_renormalization(payload) and _renormalization_budget.try_take():
            return False
        age = self._age_seconds(payload)
        return age is not None and age <= self.fresh_seconds

    def _write(self, company: GlobalCompany) -> None:
        sources = [asdict(source) for source in _cache_sources(company)]
        official = bool(_official_sources(company))
        payload = {
            "schemaVersion": CACHE_SCHEMA_VERSION,
            "normalizerRevision": NORMALIZER_REVISION,
            "identity": {
                "country": company.country,
                "exchange": company.exchange,
                "mic_code": company.mic_code,
                "ticker": company.ticker,
                "isin": company.isin,
                "lei": company.lei,
            },
            "provider": self.upstream_id,
            "fetchedAt": _utc_now().isoformat(),
            "officialEvidence": official,
            "filingPeriodEnd": company.filing_period_end,
            "fundamentals": {field: getattr(company, field) for field in _FUNDAMENTAL_FIELDS},
            "raw_provider_fields": company.raw_provider_fields,
            "sources": sources,
            "evidenceContract": fundamental_evidence_contract(company),
        }
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        write_bulk_text(self._latest_path(company), text)

        archive = self._archive_path(company, company.filing_period_end)
        if not archive.exists() or official:
            write_bulk_text(archive, text)

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

        # Cached provider diagnostics are useful, but any fresh market/catalog
        # fields already on the seed take precedence over stale cached metadata.
        raw_fields = dict(payload.get("raw_provider_fields") or {})
        raw_fields.update(seed.raw_provider_fields)
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

    def _current_official(self, payload: Optional[dict]) -> bool:
        return (
            payload is not None
            and bool(payload.get("officialEvidence"))
            and bool(_payload_official_sources(payload))
            and not self._stale_official_filing(payload)
        )

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        cached = self._read(company)
        if cached is not None and bool(cached.get("officialEvidence")) and self._is_fresh(cached):
            return self._decode(company, cached, fallback=False)
        try:
            enriched = self.upstream.enrich_fundamentals(company)
        except Exception as exc:
            # Outage resilience must not resurrect an obsolete official filing:
            # stale annual evidence is less trustworthy than an explicit block.
            if cached is not None and not self._stale_official_filing(cached):
                return self._decode(company, cached, fallback=True)
            if isinstance(exc, GlobalProviderError):
                raise
            raise GlobalProviderError(f"fundamentals unavailable and no cache exists: {type(exc).__name__}: {str(exc)[:120]}") from exc
        if not _official_sources(enriched) and self._current_official(cached):
            # Never let a weaker (vendor/non-official) refresh overwrite a
            # still-current official snapshot. Serve the official snapshot and
            # record why; the vendor result is not persisted over it.
            preserved = self._decode(company, cached, fallback=True)
            return replace(preserved, raw_provider_fields={
                **preserved.raw_provider_fields,
                "fundamentals_official_preserved": True,
                "fundamentals_refresh_non_official_provider": ",".join(
                    sorted({s.provider for s in enriched.sources if "financial" in s.source_type or "fundamental" in s.source_type})
                ) or None,
            })
        self._write(enriched)
        return enriched
