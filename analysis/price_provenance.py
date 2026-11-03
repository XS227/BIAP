"""Per-price provenance for listed-company detail responses (additive, read-only).

The stored company record can carry a price from the day the record was first enriched
(e.g. Pekarman 7,170 on 2026-09-12) while Kiasha/TSETMC observed a newer one (9,410 on
2026-10-29).  Nothing is overwritten: this module only *labels* every price with where it
came from and when, and lists the append-only observations that already exist in
market-memory, so the app can show "this price is N days old" instead of a bare number.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

STALE_AFTER_HOURS = 36.0


def _iso_from_epoch(value: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _parse(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _entry(label: str, price: Any, source: Any, observed_at: Optional[str], now: datetime) -> dict:
    observed = _parse(observed_at)
    age_hours = round((now - observed).total_seconds() / 3600, 1) if observed else None
    if price is None:
        status = "missing"
    elif age_hours is None:
        status = "unknown_time"
    elif age_hours < 0 or age_hours > STALE_AFTER_HOURS:
        status = "stale"
    else:
        status = "fresh"
    return {"label": label, "price": price, "source": source, "observedAt": observed_at, "ageHours": age_hours, "status": status}


def build_price_provenance(
    stored_market: dict | None,
    memory: dict | None,
    history: list[dict] | None,
    *,
    now: datetime | None = None,
) -> dict:
    """Label the stored price and the newest persisted observation; never changes either."""
    current = now or datetime.now(timezone.utc)
    market = stored_market or {}
    stored = _entry(
        "company_record", market.get("price"), market.get("price_source") or "company_record",
        _iso_from_epoch(market.get("quote_fetched_at")), current,
    )
    newest = None
    if memory:
        newest = _entry("market_memory_latest", memory.get("price"), memory.get("source"), memory.get("observed_at"), current)
    candidates = [e for e in (stored, newest) if e and e["price"] is not None and _parse(e["observedAt"])]
    best = max(candidates, key=lambda e: _parse(e["observedAt"]), default=None)
    gap = None
    if stored["price"] is not None and newest and newest["price"] is not None and stored["price"] != newest["price"]:
        gap = {"storedPrice": stored["price"], "newestPrice": newest["price"], "storedObservedAt": stored["observedAt"], "newestObservedAt": newest["observedAt"]}
    return {
        "storedPrice": stored,
        "latestObservation": newest,
        "mostRecent": best,
        "disagreement": gap,
        "history": [
            {"observedAt": h.get("observed_at"), "price": h.get("price"), "source": h.get("source")}
            for h in (history or []) if h.get("price") is not None
        ],
        "note": "Prices are labelled, never overwritten; history is append-only market-memory.",
    }
