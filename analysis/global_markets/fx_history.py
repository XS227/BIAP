"""Date-aligned historical FX conversion from the ECB euro reference rates.

Valuation ratios of a cross-currency reporter (a SEK-listed company reporting
in EUR, an LSE line reporting in USD) mix a quote currency with filing figures
in another currency. Converting is only honest when each quantity is converted
at the rate that belongs to *its own date*:

* balance-sheet items (equity, debt, cash) are instants -> the reference rate
  on the balance-sheet date (``rate``);
* flow items (EPS, EBITDA, dividends) accrue over the fiscal year -> the mean
  of the reference rates of that year (``average``).

Every conversion returns an :class:`FXQuote` carrying provider, the rate date
actually used, the requested date and the number of observations, so the
currency provenance can be stored next to the derived ratio. A date without a
published rate within ``max_gap_days`` *before* it (weekends, holidays) raises:
a future rate is never used and nothing falls back to an undated "latest" rate.

Data: ``eurofxref-hist.xml`` (official ECB history, EUR base). It is compacted to
a JSON cache under ``$BIAP_GLOBAL_DATA_DIR/fx/ecb-hist.json``. Reads never touch
the network; ``refresh`` does and is called by the operator/scan refresh job.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

from .providers import GlobalProviderError

PROVIDER_ID = "ecb-euro-reference-rates-historical"
ECB_HIST_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml"
DEFAULT_MAX_GAP_DAYS = 7
DEFAULT_KEEP_YEARS = 6
_DAY_RE = re.compile(r"<Cube\s+time=['\"](\d{4}-\d{2}-\d{2})['\"]\s*>(.*?)</Cube>", re.S)
_RATE_RE = re.compile(r"<Cube\s+currency=['\"]([A-Z]{3})['\"]\s+rate=['\"]([0-9.]+)['\"]")


@dataclass(frozen=True)
class FXQuote:
    base: str            # currency being converted from
    quote: str           # currency converted into
    rate: float          # value of 1 base in quote
    kind: str            # "spot" | "period_average"
    requested: str       # requested date (spot) or "start/end" (average)
    rate_date: str       # date of the ECB fixing used (spot) or last fixing in the window
    observations: int
    provider: str = PROVIDER_ID

    def as_dict(self) -> dict:
        return asdict(self)


def parse_ecb_history(xml_text: str, *, keep_since: Optional[date] = None) -> dict[str, dict[str, float]]:
    """Parse ``eurofxref-hist.xml`` into ``{date: {currency: units per 1 EUR}}``."""
    table: dict[str, dict[str, float]] = {}
    for day, body in _DAY_RE.findall(xml_text):
        if keep_since is not None and date.fromisoformat(day) < keep_since:
            continue
        rates = {code: float(rate) for code, rate in _RATE_RE.findall(body) if float(rate) > 0}
        if rates:
            table[day] = rates
    return table


def _default_path() -> Path:
    override = os.environ.get("BIAP_GLOBAL_FX_HISTORY_PATH")
    if override:
        return Path(override).expanduser()
    root = os.environ.get("BIAP_GLOBAL_DATA_DIR") or "/var/lib/biap-global"
    return Path(root).expanduser() / "fx" / "ecb-hist.json"


class ECBHistoricalFX:
    provider_id = PROVIDER_ID

    def __init__(self, path: Optional[Path] = None, *, max_gap_days: int = DEFAULT_MAX_GAP_DAYS,
                 fetcher: Optional[Callable[[], str]] = None) -> None:
        self.path = Path(path) if path is not None else _default_path()
        self.max_gap_days = max_gap_days
        self._fetcher = fetcher
        self._table: Optional[dict[str, dict[str, float]]] = None
        self._days: list[str] = []
        self.fetched_at: Optional[str] = None

    # -- storage -------------------------------------------------------
    def load(self) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            table = payload["rates"]
            if not isinstance(table, dict) or not table:
                return False
        except (OSError, ValueError, KeyError, TypeError):
            return False
        self._table = {d: {c: float(r) for c, r in rates.items()} for d, rates in table.items()}
        self._days = sorted(self._table)
        self.fetched_at = payload.get("fetchedAt")
        return True

    def available(self) -> bool:
        return self._table is not None or self.load()

    def refresh(self, *, years: int = DEFAULT_KEEP_YEARS, xml_text: Optional[str] = None) -> dict:
        """Download the official history and rewrite the compact cache atomically."""
        if xml_text is None:
            if self._fetcher is not None:
                xml_text = self._fetcher()
            else:
                import httpx
                try:
                    with httpx.Client(timeout=60.0, headers={"Accept": "application/xml"}) as client:
                        response = client.get(ECB_HIST_URL)
                    response.raise_for_status()
                    xml_text = response.text
                except httpx.HTTPError as exc:
                    raise GlobalProviderError(f"ECB historical reference rates request failed: {type(exc).__name__}") from exc
        keep_since = date.today() - timedelta(days=365 * years)
        table = parse_ecb_history(xml_text, keep_since=keep_since)
        if len(table) < 200:
            raise GlobalProviderError("ECB historical reference rates response had too few fixings")
        payload = {
            "provider": PROVIDER_ID, "sourceUrl": ECB_HIST_URL,
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "firstDate": min(table), "lastDate": max(table), "days": len(table), "rates": table,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temp.replace(self.path)
        self._table, self._days, self.fetched_at = table, sorted(table), payload["fetchedAt"]
        return {k: payload[k] for k in ("firstDate", "lastDate", "days", "fetchedAt")}

    # -- lookups -------------------------------------------------------
    def _cross(self, rates: dict[str, float], base: str, quote: str) -> float:
        value = dict(rates, EUR=1.0)
        for code in (base, quote):
            if code not in value:
                raise GlobalProviderError(f"ECB publishes no reference rate for {code}")
        return value[quote] / value[base]

    def _require(self) -> None:
        if not self.available():
            raise GlobalProviderError("ECB historical FX cache is not available (run fx_history refresh)")

    def _fixing_on_or_before(self, on: date) -> tuple[str, dict[str, float]]:
        import bisect
        iso = on.isoformat()
        idx = bisect.bisect_right(self._days, iso) - 1
        if idx < 0:
            raise GlobalProviderError(f"no ECB fixing on or before {iso}")
        day = self._days[idx]
        if (on - date.fromisoformat(day)).days > self.max_gap_days:
            raise GlobalProviderError(f"no ECB fixing within {self.max_gap_days} days before {iso} (latest {day})")
        return day, self._table[day]  # type: ignore[index]

    def rate(self, base_currency: str, quote_currency: str, on: date) -> FXQuote:
        """Spot: value of 1 ``base`` in ``quote`` on ``on`` (latest fixing not after it)."""
        base, quote = base_currency.strip().upper(), quote_currency.strip().upper()
        self._require()
        if base == quote:
            return FXQuote(base, quote, 1.0, "spot", on.isoformat(), on.isoformat(), 0)
        day, rates = self._fixing_on_or_before(on)
        return FXQuote(base, quote, self._cross(rates, base, quote), "spot", on.isoformat(), day, 1)

    def average(self, base_currency: str, quote_currency: str, start: date, end: date, *, min_observations: int = 150) -> FXQuote:
        """Mean of the daily crosses published between ``start`` and ``end`` inclusive."""
        base, quote = base_currency.strip().upper(), quote_currency.strip().upper()
        self._require()
        if end < start:
            raise GlobalProviderError("FX averaging window is inverted")
        if base == quote:
            return FXQuote(base, quote, 1.0, "period_average", f"{start}/{end}", end.isoformat(), 0)
        s, e = start.isoformat(), end.isoformat()
        values: list[float] = []
        last = ""
        for day in self._days:
            if s <= day <= e:
                try:
                    values.append(self._cross(self._table[day], base, quote))  # type: ignore[index]
                except GlobalProviderError:
                    continue
                last = day
        span_days = (end - start).days + 1
        needed = min(min_observations, max(1, int(span_days * 0.6 * 5 / 7)))
        if len(values) < needed:
            raise GlobalProviderError(
                f"only {len(values)} ECB fixings for {base}/{quote} in {s}..{e} (need >= {needed})"
            )
        if (end - date.fromisoformat(last)).days > self.max_gap_days:
            raise GlobalProviderError(f"ECB history ends {last}, before the averaging window end {e}")
        return FXQuote(base, quote, sum(values) / len(values), "period_average", f"{s}/{e}", last, len(values))


_DEFAULT: Optional[ECBHistoricalFX] = None


def default_provider() -> ECBHistoricalFX:
    """Process-wide cache-reading provider (never hits the network)."""
    global _DEFAULT
    path = _default_path()
    if _DEFAULT is None or _DEFAULT.path != path:
        _DEFAULT = ECBHistoricalFX(path)
    return _DEFAULT


def main(argv: Optional[Iterable[str]] = None) -> int:
    import sys
    args = list(argv if argv is not None else sys.argv[1:])
    provider = ECBHistoricalFX()
    if args[:1] == ["refresh"]:
        print(json.dumps(provider.refresh(), indent=2))
        return 0
    if provider.load():
        print(json.dumps({"path": str(provider.path), "fetchedAt": provider.fetched_at, "days": len(provider._days),
                          "first": provider._days[0], "last": provider._days[-1]}, indent=2))
        return 0
    print("no cache; run: python -m global_markets.fx_history refresh")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
