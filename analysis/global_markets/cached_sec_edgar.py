"""Persistent raw SEC EDGAR cache for BIAP Global.

SEC ``companyfacts`` responses contain historical annual facts, not only the
latest normalized BIAP metrics. Keeping the verified JSON on the Global server
means previously fetched US company history remains locally available during a
temporary SEC outage and can support richer historical normalization later.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Optional

from .providers import GlobalProviderError
from .sec_edgar import SECEdgarFundamentalsProvider, SEC_FACTS_BASE, SEC_TICKERS_URL
from .source_cache import data_root, read_json, write_json_atomic


class CachedSECEdgarFundamentalsProvider(SECEdgarFundamentalsProvider):
    provider_id = "sec-edgar-xbrl-cached"

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return data_root() / "cache" / "sec-edgar" / f"{digest}.json"

    @staticmethod
    def _age_seconds(fetched_at: str) -> Optional[float]:
        try:
            parsed = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return None

    def _get_json(self, url: str) -> dict:
        path = self._cache_path(url)
        cached = read_json(path)
        # Ticker mapping changes less often than issuer facts. Company facts are
        # refreshed daily so newly filed 10-K/10-K-A data becomes visible fast.
        ttl = 7 * 24 * 3600 if url == SEC_TICKERS_URL else 24 * 3600
        if isinstance(cached, dict) and isinstance(cached.get("payload"), dict):
            age = self._age_seconds(str(cached.get("fetchedAt") or ""))
            if age is not None and age <= ttl:
                return cached["payload"]

        try:
            payload = super()._get_json(url)
        except GlobalProviderError:
            if isinstance(cached, dict) and isinstance(cached.get("payload"), dict):
                return cached["payload"]
            raise

        write_json_atomic(path, {
            "source": "SEC EDGAR companyfacts" if url.startswith(SEC_FACTS_BASE) else "SEC ticker mapping",
            "url": url,
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        })
        return payload
