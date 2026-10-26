"""TIndex daily candles for the tse-market and tse-sectors index series only.

TIndex's public API no longer serves per-stock data (the stock categories answer 410 or do not
exist), so stock prices stay on TSETMC. ``by-category/tse-market`` and ``by-category/tse-sectors``
still work (verified 2026-10-22: 9 + 26 series under ``data.rows``). This module only keeps those
~35 Tehran-exchange index/sector series current, within the free plan (3 req/min, 300 req/day,
counted per account). It is resumable: every run picks up the least-recently-fetched series.

Every stored row carries source="TIndex"; consumers must show SOURCE_ATTRIBUTION next to the numbers.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://tindex.app/api/public"
CATEGORIES = ("tse-market", "tse-sectors")
USER_AGENT = "BIAP-baseline/1.0 (+https://biap.dadashi.no)"
SOURCE_ATTRIBUTION = {"name": "TIndex", "url": "https://tindex.app"}
REQUEST_INTERVAL_SECONDS = 21.0  # 3 req/min plan -> 20 s minimum, plus margin
DAILY_CAP = 250  # plan allows 300/day (429s are not counted); keep headroom for other users of the account
MAX_CONSECUTIVE_429 = 3
DEFAULT_DB = Path(__file__).with_name("tindex_indices.sqlite3")


class TindexRateLimited(RuntimeError):
    def __init__(self, retry_after: Optional[float]) -> None:
        super().__init__(f"TIndex 429 (retry_after={retry_after})")
        self.retry_after = retry_after


def _token() -> str:
    value = os.environ.get("TINDEX_API_TOKEN", "").strip()
    if not value:
        path = Path(os.environ.get("TINDEX_KEY_FILE", str(Path.home() / ".tindex_key")))
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            value = ""
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tindex_series (
            slug TEXT PRIMARY KEY, category TEXT NOT NULL, name TEXT, last_fetched_at TEXT, last_error TEXT);
        CREATE TABLE IF NOT EXISTS tindex_candles (
            slug TEXT NOT NULL, day INTEGER NOT NULL, open REAL, high REAL, low REAL, close REAL,
            source TEXT NOT NULL DEFAULT 'TIndex', fetched_at TEXT NOT NULL, PRIMARY KEY (slug, day));
        CREATE TABLE IF NOT EXISTS tindex_quota (utc_date TEXT PRIMARY KEY, requests INTEGER NOT NULL);
        """
    )
    return conn


def _get(path: str) -> Any:
    token = _token()
    if not token:
        raise RuntimeError("TIndex token not configured")
    # Cloudflare in front of tindex.app rejects urllib's default "Python-urllib/x" agent with error 1010 (403).
    req = Request(
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 429:
            retry_after = None
            try:
                retry_after = float(exc.headers.get("Retry-After"))
            except (TypeError, ValueError):
                pass
            raise TindexRateLimited(retry_after) from exc
        raise
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"TIndex request failed: {exc}") from exc


def decode_candles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Decode the compact candle arrays. ``t`` is days since 1970-01-01 for the first element and
    day deltas after it; o/h/l/c are absolute values (verified 2026-10-22 on tse-sector-etf: last
    close 134 vs current 134.18). Values are rounded to the series' ``decimals`` and the series is
    close-only (o == h == l == c), so consumers must not present it as true OHLC."""
    t, o, h, l, c = (payload.get(k) or [] for k in ("t", "o", "h", "l", "c"))
    if not (len(t) == len(o) == len(h) == len(l) == len(c)):
        raise ValueError("TIndex candle arrays have different lengths")
    rows, day = [], 0
    for i, delta in enumerate(t):
        day = int(delta) if i == 0 else day + int(delta)
        rows.append({"day": day, "open": o[i], "high": h[i], "low": l[i], "close": c[i]})
    return rows


def _walk_series(node: Any, found: dict[str, dict[str, str]]) -> None:
    if isinstance(node, dict):
        slug, category = node.get("slug"), str(node.get("category") or node.get("category_slug") or "")
        if slug and category in CATEGORIES:
            found[str(slug)] = {"category": category, "name": str(node.get("name") or node.get("title") or "")}
        for value in node.values():
            _walk_series(value, found)
    elif isinstance(node, list):
        for value in node:
            _walk_series(value, found)


def discover_series(
    *, sleep: Callable[[float], None] = time.sleep, on_request: Callable[[], None] = lambda: None
) -> dict[str, dict[str, str]]:
    """Find index slugs from ``data.rows`` of each category; fall back to the market board on 410.

    ``on_request`` is called once per HTTP request so the caller's daily quota stays accurate.
    """
    found: dict[str, dict[str, str]] = {}
    for category in CATEGORIES:
        try:
            on_request()
            payload = _get(f"/indicators/by-category/{category}")
            data = payload.get("data") if isinstance(payload, dict) else None
            rows = data.get("rows") if isinstance(data, dict) else data
            for item in rows or []:
                if isinstance(item, dict) and item.get("slug"):
                    found[str(item["slug"])] = {"category": category, "name": str(item.get("name") or "")}
        except HTTPError as exc:
            if exc.code != 410:
                raise
        sleep(REQUEST_INTERVAL_SECONDS)
    if not found:
        on_request()
        _walk_series(_get("/boards/market"), found)
    return found


def _used_today(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT requests FROM tindex_quota WHERE utc_date=?", (datetime.now(timezone.utc).date().isoformat(),)).fetchone()
    return int(row["requests"]) if row else 0


def _count_request(conn: sqlite3.Connection) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    conn.execute(
        "INSERT INTO tindex_quota(utc_date,requests) VALUES(?,1) ON CONFLICT(utc_date) DO UPDATE SET requests=requests+1", (today,)
    )
    conn.commit()


def run(*, db_path: Path = DEFAULT_DB, daily_cap: int = DAILY_CAP, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Fetch candles for the least-recently-fetched series until the daily cap or a 3x 429."""
    result: dict[str, Any] = {"source": "TIndex", "succeeded": 0, "failed": 0, "rateLimited": 0, "stoppedEarly": None}
    conn = _connect(db_path)
    try:
        if _used_today(conn) >= daily_cap:
            result["stoppedEarly"] = f"TIndex daily cap reached ({daily_cap})"
        else:
            if not conn.execute("SELECT 1 FROM tindex_series LIMIT 1").fetchone():
                for slug, meta in discover_series(sleep=sleep, on_request=lambda: _count_request(conn)).items():
                    conn.execute("INSERT OR IGNORE INTO tindex_series(slug,category,name) VALUES(?,?,?)", (slug, meta["category"], meta["name"]))
                conn.commit()
            queue = [r["slug"] for r in conn.execute("SELECT slug FROM tindex_series ORDER BY last_fetched_at IS NOT NULL, last_fetched_at, slug")]
            consecutive_429 = 0
            for slug in queue:
                if _used_today(conn) >= daily_cap:
                    result["stoppedEarly"] = f"TIndex daily cap reached ({daily_cap})"
                    break
                try:
                    _count_request(conn)
                    payload = _get(f"/indicators/{slug}/candles?range=3m&interval=daily")
                    rows = decode_candles(payload.get("data") if isinstance(payload.get("data"), dict) else payload)
                    now = _now()
                    conn.executemany(
                        "INSERT OR REPLACE INTO tindex_candles(slug,day,open,high,low,close,source,fetched_at) VALUES(?,?,?,?,?,?,'TIndex',?)",
                        [(slug, r["day"], r["open"], r["high"], r["low"], r["close"], now) for r in rows],
                    )
                    conn.execute("UPDATE tindex_series SET last_fetched_at=?, last_error=NULL WHERE slug=?", (now, slug))
                    conn.commit()
                    result["succeeded"] += 1
                    consecutive_429 = 0
                except TindexRateLimited as exc:
                    result["rateLimited"] += 1
                    consecutive_429 += 1
                    if consecutive_429 >= MAX_CONSECUTIVE_429:
                        result["stoppedEarly"] = f"TIndex rate limit: {consecutive_429} consecutive 429s"
                        break
                    sleep((exc.retry_after if exc.retry_after is not None else 60.0) + 2.0)
                    continue
                except (RuntimeError, ValueError, HTTPError) as exc:
                    result["failed"] += 1
                    conn.execute("UPDATE tindex_series SET last_error=? WHERE slug=?", (str(exc)[:300], slug))
                    conn.commit()
                sleep(REQUEST_INTERVAL_SECONDS)
        result["remaining"] = conn.execute(
            "SELECT COUNT(*) FROM tindex_series WHERE last_fetched_at IS NULL OR last_fetched_at < ?",
            (datetime.now(timezone.utc).date().isoformat(),),
        ).fetchone()[0]
        result["requestsToday"] = _used_today(conn)
    finally:
        conn.close()
    return result


def latest_with_source(slug: str, *, db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    """Latest stored candle for API responses; always carries the attribution the UI must render."""
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM tindex_candles WHERE slug=? ORDER BY day DESC LIMIT 1", (slug,)).fetchone()
    finally:
        conn.close()
    return {"slug": slug, "candle": dict(row) if row else None, "source": SOURCE_ATTRIBUTION}
