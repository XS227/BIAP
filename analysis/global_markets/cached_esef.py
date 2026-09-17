"""Persistent server cache for the conservative ESEF fundamentals adapter."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Optional

from .esef import FILINGS_API
from .esef_country import CountryAwareESEFFundamentalsProvider
from .providers import GlobalProviderError
from .source_cache import data_root, read_json, write_json_atomic


class CachedESEFFundamentalsProvider(CountryAwareESEFFundamentalsProvider):
    provider_id = "esef-xbrl-cached"

    def _cache_path(self, url: str, params: Optional[dict]) -> Path:
        canonical = json.dumps({"url": url, "params": params or {}}, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return data_root() / "cache" / "esef" / f"{digest}.json"

    @staticmethod
    def _age_seconds(fetched_at: str) -> Optional[float]:
        try:
            parsed = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return None

    def _get_json(self, url: str, *, params: Optional[dict] = None) -> dict:
        path = self._cache_path(url, params)
        cached = read_json(path)
        ttl = 6 * 3600 if url.startswith(FILINGS_API) else 30 * 24 * 3600
        if isinstance(cached, dict) and isinstance(cached.get("payload"), dict):
            age = self._age_seconds(str(cached.get("fetchedAt") or ""))
            if age is not None and age <= ttl:
                return cached["payload"]

        try:
            payload = super()._get_json(url, params=params)
        except GlobalProviderError:
            # A previously verified response may be used as stale evidence input;
            # the Evidence Agent still evaluates price/fundamental freshness.
            if isinstance(cached, dict) and isinstance(cached.get("payload"), dict):
                return cached["payload"]
            raise

        write_json_atomic(path, {
            "source": "filings.xbrl.org ESEF/UKSEF",
            "url": url,
            "params": params or {},
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        })
        return payload
