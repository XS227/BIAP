"""Latest interim (10-Q) and trailing-twelve-month evidence from SEC companyfacts.

Reads only the companyfacts payload the annual adapter has already fetched; it
makes no request of its own. The result is a separately labelled block that is
NEVER merged into the annual figures: annual-only scoring and the
LAST_ANNUAL_FILING freshness gate are unchanged by it.

Rules that keep it honest:
* only rows of Form 10-Q / 10-Q/A are interim facts, and only those of the
  newest 10-Q accession (one filing, never a mix of filings);
* flow items use the cumulative fiscal year-to-date (YTD) figure, so quarters
  are never summed (no double counting of Q1 inside a Q2 YTD);
* TTM = latest annual + current YTD - prior-year YTD, and only when the YTD
  starts the day after the annual period ended (fiscal-period boundary) and
  the prior-year comparative covers the same span; otherwise TTM is withheld
  with the reason and the YTD is still shown;
* balance-sheet items are instants at the interim period end, same accession.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

INTERIM_FORMS = {"10-Q", "10-Q/A"}
REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
)
NET_INCOME_TAGS = ("NetIncomeLoss", "ProfitLoss")
OCF_TAGS = ("NetCashProvidedByUsedInOperatingActivities",)
ASSET_TAGS = ("Assets",)
LIABILITY_TAGS = ("Liabilities",)
EQUITY_TAGS = (
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity",
)
_FLOWS = {"revenue": REVENUE_TAGS, "netIncome": NET_INCOME_TAGS, "operatingCashFlow": OCF_TAGS}
_BALANCES = {"totalAssets": ASSET_TAGS, "totalLiabilities": LIABILITY_TAGS, "totalEquity": EQUITY_TAGS}

LABEL = "LATEST_INTERIM_10Q_UNAUDITED"
SCORING_NOTE = "informational only: annual-only scoring and LAST_ANNUAL_FILING gate are unchanged"
_BOUNDARY_TOLERANCE_DAYS = 4
_COMPARATIVE_TOLERANCE_DAYS = 10


def _day(value: object) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _interim_rows(concept: object) -> list[dict]:
    units = concept.get("units") if isinstance(concept, dict) else None
    if not isinstance(units, dict):
        return []
    rows: list[dict] = []
    for unit, entries in units.items():
        if not isinstance(entries, list):
            continue
        for row in entries:
            if (
                isinstance(row, dict)
                and isinstance(row.get("val"), (int, float))
                and not isinstance(row.get("val"), bool)
                and str(row.get("form") or "").upper() in INTERIM_FORMS
                and _day(row.get("end")) is not None
            ):
                rows.append({**row, "_unit": str(unit)})
    return rows


def _latest_accession(gaap: dict, annual_end: date) -> Optional[tuple[str, date, dict]]:
    """Newest 10-Q accession whose period ends after the annual period."""
    best: Optional[tuple[date, str, str]] = None
    for tags in (*_FLOWS.values(), *_BALANCES.values()):
        for tag in tags:
            for row in _interim_rows(gaap.get(tag)):
                end = _day(row["end"])
                if end is None or end <= annual_end or not row.get("accn"):
                    continue
                key = (end, str(row.get("filed") or ""), str(row["accn"]))
                if best is None or key > best:
                    best = key
    if best is None:
        return None
    end, filed, accn = best
    return accn, end, {"filed": filed or None}


def _pick(rows: list[dict], *, accn: str, end: date) -> list[dict]:
    return [r for r in rows if str(r.get("accn")) == accn and _day(r["end"]) == end]


def _flow_value(row: Optional[dict]) -> Optional[float]:
    return float(row["val"]) if row else None


def build_interim_evidence(
    gaap: object,
    annual_period_end: Optional[str],
    annual_values: Optional[dict] = None,
    *,
    source_url: Optional[str] = None,
) -> Optional[dict]:
    """Interim/TTM block, or None when no 10-Q newer than the annual exists."""
    if not isinstance(gaap, dict):
        return None
    annual_end = _day(annual_period_end) if annual_period_end else None
    if annual_end is None:
        return None
    latest = _latest_accession(gaap, annual_end)
    if latest is None:
        return None
    accn, end, meta = latest

    ytd: dict = {}
    quarter: dict = {}
    prior: dict = {}
    units: dict = {}
    starts: set[date] = set()
    tags_used: dict = {}
    fiscal: dict = {}
    for name, tags in _FLOWS.items():
        for tag in tags:
            rows = [r for r in _pick(_interim_rows(gaap.get(tag)), accn=accn, end=end) if _day(r.get("start"))]
            if not rows:
                continue
            by_len = sorted(rows, key=lambda r: (end - _day(r["start"])).days)
            longest = by_len[-1]
            span = (end - _day(longest["start"])).days
            ytd[name] = longest
            tags_used[name] = tag
            units[name] = longest["_unit"]
            starts.add(_day(longest["start"]))
            fiscal = {"fiscalYear": longest.get("fy"), "fiscalPeriod": longest.get("fp"), "form": longest.get("form")}
            discrete = [r for r in by_len if 70 <= (end - _day(r["start"])).days <= 110]
            if discrete and span > 110:
                quarter[name] = discrete[-1]
            elif span <= 110:
                quarter[name] = longest
            # Prior-year comparative: same tag/unit, same span, one year earlier.
            target_start = _day(longest["start"])
            for comp in _interim_rows(gaap.get(tag)):
                c_start, c_end = _day(comp.get("start")), _day(comp["end"])
                if c_start is None or comp["_unit"] != longest["_unit"]:
                    continue
                if (
                    abs((end - c_end).days - 365) <= _COMPARATIVE_TOLERANCE_DAYS
                    and abs((c_end - c_start).days - span) <= _COMPARATIVE_TOLERANCE_DAYS
                    and abs((target_start - c_start).days - 365) <= _COMPARATIVE_TOLERANCE_DAYS
                ):
                    if name not in prior or str(comp.get("filed") or "") > str(prior[name].get("filed") or ""):
                        prior[name] = comp
            break

    balance: dict = {}
    for name, tags in _BALANCES.items():
        for tag in tags:
            rows = _pick(_interim_rows(gaap.get(tag)), accn=accn, end=end)
            if rows:
                balance[name] = {"value": float(rows[0]["val"]), "unit": rows[0]["_unit"], "tag": tag}
                break

    if not ytd and not balance:
        return None

    def view(rows: dict) -> dict:
        return {k: _flow_value(v) for k, v in rows.items()}

    ytd_start = max(starts) if starts else None
    ttm: Optional[dict] = None
    ttm_reason: Optional[str] = None
    annual_values = annual_values or {}
    if ytd_start is None:
        ttm_reason = "no interim flow facts available"
    else:
        gap = (ytd_start - annual_end).days
        if not 1 <= gap <= _BOUNDARY_TOLERANCE_DAYS:
            ttm_reason = (
                f"fiscal-period boundary: interim YTD starts {ytd_start.isoformat()} but the latest annual "
                f"ended {annual_end.isoformat()}; periods are not adjacent, TTM withheld"
            )
        else:
            values: dict = {}
            withheld: dict = {}
            for name in _FLOWS:
                annual = annual_values.get(name)
                if annual is None:
                    withheld[name] = "annual value unavailable"
                elif name not in ytd:
                    withheld[name] = "interim YTD value unavailable"
                elif name not in prior:
                    withheld[name] = "prior-year comparable YTD unavailable"
                elif _day(ytd[name]["start"]) != ytd_start:
                    withheld[name] = "YTD span differs from other flow items"
                else:
                    values[name] = float(annual) + float(ytd[name]["val"]) - float(prior[name]["val"])
            ttm = {
                "label": "TTM = latest annual + current YTD - prior-year YTD (no quarters summed)",
                "values": values,
                "withheld": withheld,
                "components": {
                    name: {
                        "annual": float(annual_values[name]),
                        "ytd": float(ytd[name]["val"]),
                        "priorYearYtd": float(prior[name]["val"]),
                        "priorYtdPeriod": f"{prior[name].get('start')}..{prior[name].get('end')}",
                    }
                    for name in values
                },
                "annualPeriodEnd": annual_end.isoformat(),
                "periodEnd": end.isoformat(),
            }
            if not values:
                ttm_reason = "no metric has annual, YTD and prior-year YTD components"

    return {
        "label": LABEL,
        "scoringUse": SCORING_NOTE,
        "periodEnd": end.isoformat(),
        "annualPeriodEnd": annual_end.isoformat(),
        **fiscal,
        "accession": accn,
        "filed": meta.get("filed"),
        "sourceUrl": source_url,
        "audited": False,
        "ytd": {
            "start": ytd_start.isoformat() if ytd_start else None,
            "end": end.isoformat(),
            "values": view(ytd),
            "units": units,
            "tags": tags_used,
        },
        "quarter": view(quarter),
        "priorYearYtd": view(prior),
        "balance": balance,
        "ttm": ttm,
        "ttmWithheldReason": ttm_reason,
    }
