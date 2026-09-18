"""Durable per-provider daily price history for BIAP Global.

Each provider keeps its own file so future reconciliation can compare licensed
and public sources without silently mixing them. Existing dates are merged with
new observations; temporary upstream outages never delete older history.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import GlobalCompany
from .source_cache import data_root, read_json, write_json_atomic


def _slug(value: str) -> str:
    return "".join(ch for ch in str(value).upper() if ch.isalnum() or ch in {"-", "_"}) or "UNKNOWN"


def _provider_slug(value: str) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum() or ch in {"-", "_"}) or "provider"


def _date_key(row: dict[str, Any]) -> str | None:
    raw = row.get("date") or row.get("datetime") or row.get("timestamp")
    if raw in (None, ""):
        return None
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(raw).strip()
    if not text:
        return None
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def history_path(company: GlobalCompany, provider_id: str) -> Path:
    return (
        data_root()
        / "history"
        / _slug(company.country)
        / _slug(company.exchange)
        / _slug(company.ticker)
        / f"{_provider_slug(provider_id)}.json"
    )


def persist_daily_history(
    company: GlobalCompany,
    provider_id: str,
    rows: Iterable[dict[str, Any]],
    *,
    metadata: dict[str, Any] | None = None,
    max_points: int = 3000,
) -> bool:
    """Merge verified daily observations into a durable server-side history file.

    The function is best-effort by design: a read-only filesystem must never
    turn an otherwise valid market-data response into an API failure.
    """

    path = history_path(company, provider_id)
    existing = read_json(path, default={})
    points: dict[str, dict[str, Any]] = {}

    if isinstance(existing, dict):
        for row in existing.get("points") or []:
            if isinstance(row, dict):
                key = _date_key(row)
                if key:
                    points[key] = {**row, "date": key}

    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _date_key(row)
        if not key:
            continue
        clean = {"date": key}
        for field in ("open", "high", "low", "close", "adjusted_close", "volume"):
            value = row.get(field)
            if value is not None:
                clean[field] = value
        points[key] = clean

    if not points:
        return False

    ordered = [points[key] for key in sorted(points)][-max(1, int(max_points)):]
    payload = {
        "schemaVersion": 1,
        "identity": {
            "country": company.country,
            "exchange": company.exchange,
            "mic": company.mic_code,
            "ticker": company.ticker,
            "currency": company.currency,
        },
        "provider": provider_id,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
        "points": ordered,
    }
    try:
        write_json_atomic(path, payload)
    except OSError:
        return False
    return True
