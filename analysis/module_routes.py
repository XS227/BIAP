"""Unified module-data service for the Iran app: one resolver, one dataset builder, one contract per module.

GET  /iran/modules/{code}/dataset         normalized market + CODAL dataset with provenance/quality
GET  /iran/modules/{code}/readiness       every module's contract status for this company
POST /iran/modules/{code}/{module}        compute a module (blocks the app renders generically)
GET  /iran/sql/schema | POST /iran/sql/query | POST /iran/sql/export
/iran/crm/*                               private CRM + KPI register (user-scoped)
GET  /iran/coverage                       whole-universe data coverage and reasons
"""
from __future__ import annotations

import logging
import re
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

import module_compute as mc
import module_dataset as md
from module_dataset import symbol_key
import private_analytics
import safe_sql
from auth import require_user_id
from business_dataset_store import get_dataset
from listed_company_store import ListedCompanyStore
from market_memory import history_for_symbols, recent_symbol_history
from private_store import PrivateDataError, PrivateStore

log = logging.getLogger("biap.iran.modules")


class ModuleError(Exception):
    """A typed failure: ``code`` is one of NOT_FOUND, AMBIGUOUS, SERVER_ERROR (data states live in dataset.status)."""

    def __init__(self, status: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


class _TypedRoute(APIRoute):
    """Every /iran route answers with ``{"detail": <string>, "code": <CODE>}``: no bare 500 stack traces, no generic empties."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except ModuleError as exc:
                return JSONResponse({"detail": exc.message, "code": exc.code, **exc.extra}, status_code=exc.status)
            except (HTTPException, StarletteHTTPException, RequestValidationError):
                raise  # client errors (404/422/...) keep FastAPI's normal handlers and details
            except Exception:  # noqa: BLE001 - classified, logged, and returned as a typed SERVER_ERROR
                log.exception("iran module request failed: %s %s", request.method, request.url.path)
                return JSONResponse({"detail": "خطای داخلی سرور؛ دوباره تلاش کنید.", "code": "SERVER_ERROR"}, status_code=500)

        return handler


router = APIRouter(prefix="/iran", tags=["iran-modules"], route_class=_TypedRoute)
STORE = ListedCompanyStore()
PRIVATE = PrivateStore()


def resolve_company(store: ListedCompanyStore, text: str) -> dict:
    """Resolve to the issuer's PRIMARY instrument.

    Candidates: rows whose code equals the text or whose normalized symbol (Arabic ي/ك, ZWNJ, spaces) matches.
    Duplicate stub rows keyed by the bare symbol (non-primary) never shadow the primary instrument; only two
    different primary instruments are ambiguous (409 with candidates, never a guess).
    """
    text = (text or "").strip()
    wanted = symbol_key(text)
    if not wanted:
        raise ModuleError(404, "NOT_FOUND", "company not found")
    rows = md.UNIVERSE.rows(store)
    # discovery order: instrument code / symbol -> full company name or registry alias -> unique name fragment
    cands = [r for r in rows if r["code"] == text or r.get("symbol_key") == wanted or symbol_key(r["code"]) == wanted]
    if not cands:
        cands = [r for r in rows if r.get("name_key") == wanted or wanted in (r.get("aliases") or ())]
    if not cands and len(wanted) >= 3:
        cands = [r for r in rows if r.get("is_primary", 1) and (wanted in (r.get("name_key") or "") or any(wanted in a for a in r.get("aliases") or ()))]
    if not cands:
        raise ModuleError(404, "NOT_FOUND", "company not found")
    # a candidate may be a secondary/stub instrument of an issuer whose primary instrument is stored under another code
    issuers = {r.get("issuer_id") for r in cands if r.get("issuer_id")}
    cands += [r for r in rows if r.get("issuer_id") in issuers and r.get("is_primary", 1) and r not in cands]
    primary = [r for r in cands if r.get("is_primary", 1)]
    pool = primary or cands
    if len(pool) > 1:
        loose = _loose(text)
        exact = ([r for r in pool if r["code"] == text] or [r for r in pool if r["symbol"] == text]
                 or [r for r in pool if _loose(r["symbol"]) == loose] or [r for r in pool if r.get("name_key") == wanted]
                 or [r for r in pool if r.get("symbol_key") == wanted])
        if len(exact) == 1:
            pool = exact
        elif (family := _instrument_family_base(pool)) is not None:
            pool = [family]
        else:
            rank = {md.TIER_FULL: 0, md.TIER_PARTIAL: 1, md.TIER_MARKET: 2, md.TIER_REGISTERED: 3}
            best = min(rank.get(r["tier"], 9) for r in pool)
            pool = [r for r in pool if rank.get(r["tier"], 9) == best] if not primary else pool
    if len(pool) > 1:
        raise ModuleError(409, "AMBIGUOUS", "ambiguous symbol", candidates=[
            {"code": r["code"], "symbol": r["symbol"], "name": r["name"], "market": r["market"]} for r in pool[:10]])
    return _row_by_code(store, pool[0]["code"])


def _instrument_family_base(pool: list[dict]) -> Optional[dict]:
    """Same company name, symbols that differ only by a trailing number (آریا / آریا۲ / آریا۳): the base symbol is the share.

    The registry keeps some numbered instruments of one company as separate issuers; a lookup by the company's
    full name must still land on the base share instead of failing as ambiguous. Anything less clear stays ambiguous.
    """
    # stub rows named after their own code/symbol carry no company name: they do not disprove the family
    named = [r for r in pool if r.get("name_key") not in (None, "", symbol_key(r["code"]), r.get("symbol_key"))]
    names = {r["name_key"] for r in named}
    if len(names) != 1:
        return None
    bases = [r for r in pool if all(re.fullmatch(re.escape(r["symbol_key"]) + r"[0-9۰-۹]*", o.get("symbol_key") or "") for o in pool)]
    if not bases or len({b["symbol_key"] for b in bases}) != 1:
        return None
    rank = {md.TIER_FULL: 0, md.TIER_PARTIAL: 1, md.TIER_MARKET: 2, md.TIER_REGISTERED: 3}
    best = min(rank.get(b["tier"], 9) for b in bases)
    top = [b for b in bases if rank.get(b["tier"], 9) == best]
    if len(top) > 1:
        top = [b for b in top if str(b["code"]).isdigit()]   # a real instrument code beats a symbol-spelled stub row
    return top[0] if len(top) == 1 else None


def _loose(value: Any) -> str:
    """Persian/Arabic letter forms and ZWNJ folded, spaces and case kept (narrower than symbol_key)."""
    return str(value or "").translate(str.maketrans({"ي": "ی", "ك": "ک", "\u200c": ""})).strip().lower()


def _row_by_code(store: ListedCompanyStore, code: str) -> dict:
    """The stored row with EXACTLY this code; a registry company with no stored row keeps its identity (REGISTERED_ONLY)."""
    with closing(store._connect()) as conn:
        row = conn.execute("SELECT * FROM listed_companies WHERE code=?", (code,)).fetchone()
    if row is not None:
        return store._row(row, include_company=True)
    urow = next((r for r in md.UNIVERSE.rows(store) if r["code"] == code), None)
    if urow is None:
        raise ModuleError(404, "NOT_FOUND", "company not found")
    return {"code": urow["code"], "symbol": urow["symbol"], "name": urow["name"], "market": urow["market"], "enrichedAt": None,
            "lastError": None, "company": None, "registryOnly": True}


def _history(symbol: Optional[str]) -> list[dict]:
    """Market-memory snapshots under any spelling of the symbol (Persian/Arabic yeh and kaf, ZWNJ)."""
    if not symbol:
        return []
    variants = []
    for cand in (symbol, symbol.replace("ی", "ي").replace("ک", "ك"), symbol.replace("ي", "ی").replace("ك", "ک"), symbol.replace("\u200c", "")):
        if cand not in variants:
            variants.append(cand)
    for cand in variants:
        rows = recent_symbol_history(cand, days=2200)
        if rows:
            return rows
    return []


def _fill_from_sub_symbol(main_item: dict, sub_item: dict) -> dict:
    """The main stock stays the identity, but a statement/market stored only under a numbered sub-symbol is not lost."""
    mc_, sc_ = dict(main_item.get("company") or {}), sub_item.get("company") or {}
    for key in ("codal", "codal_metadata", "data_available"):
        if not mc_.get(key) and sc_.get(key):
            mc_[key] = sc_[key]
    main_market, sub_market = mc_.get("market") or {}, sc_.get("market") or {}
    if not any(main_market.get(k) for k in ("last_price", "closing_price", "price")) and sub_market:
        mc_["market"] = sub_market
    return {**main_item, "company": mc_ or main_item.get("company")}


def dataset_for(code: str) -> dict:
    item = resolve_company(STORE, code)
    rows = md.UNIVERSE.rows(STORE)
    urow = next((r for r in rows if r["code"] == item["code"]), None)
    mapped_from = None
    if urow and urow.get("sub_of"):  # a numbered sub-symbol (فخوز2/3) is the same company as its main stock: one row per company
        main = next((r for r in rows if r["code"] == urow["sub_of"]), None)
        if main is not None:
            mapped_from = {"code": urow["code"], "symbol": urow["symbol"]}
            sub_item = item
            item, urow = _row_by_code(STORE, main["code"]), main
            item = _fill_from_sub_symbol(item, sub_item)
    if urow and urow.get("symbol"):
        item = {**item, "symbol": urow["symbol"]}  # registry symbol (some rows store the instrument code there)
    history = _history(item.get("symbol"))
    ds = md.build_company_dataset(item, history, now_iso=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if urow and urow.get("instrument_kind"):
        ds["identity"]["instrumentKind"] = urow["instrument_kind"]
    if urow and urow.get("sector") and not ds["identity"].get("sector"):
        ds["identity"]["sector"] = urow["sector"]  # TSETMC sector (sector_backfill) when the baseline quote carried none
    if mapped_from:
        ds["identity"]["mappedFrom"] = mapped_from
    return ds


def _peers(ds: dict, universe: list[dict]) -> int:
    sector = ds["identity"].get("sector")
    rows = [r for r in mc.comparable(universe, ds["identity"]["code"]) if r["code"] != ds["identity"]["code"]]
    same = [r for r in rows if sector and r.get("sector") == sector]
    return max(len(same), len(rows))


@router.get("/modules/{code}/dataset")
def module_dataset(code: str, _user: str = Depends(require_user_id)):
    return dataset_for(code)


@router.get("/modules/{code}/readiness")
def module_readiness(code: str, _user: str = Depends(require_user_id)):
    ds = dataset_for(code)
    universe = md.UNIVERSE.rows(STORE)
    return {"company": ds["identity"], "tier": ds["tier"], "modules": mc.readiness(ds, _peers(ds, universe), sum(1 for r in universe if r.get("is_primary", 1) and r.get("pe") is not None)), "quality": ds["quality"]}


@router.post("/modules/{code}/{module}")
def module_compute(code: str, module: str, params: Optional[dict] = Body(default=None), user_id: str = Depends(require_user_id)):
    if module in mc.PRIVATE_MODULES and module != "crm":
        return private_analytics.compute(module, get_dataset(user_id), PRIVATE.list_kpis(user_id))
    if module == "crm":
        return {"module": "crm", "status": "ok", "pipeline": PRIVATE.pipeline(user_id), "tier": "private"}
    if module not in mc.LISTED_MODULES:
        raise HTTPException(status_code=404, detail=f"unknown module {module}")
    ds = dataset_for(code)
    if module == "sql":
        return {"module": "sql", "status": "ok", "title": "SQL / Data Query", "schema": safe_sql.schema(), "company": ds["identity"], "tier": ds["tier"],
                "examples": _sql_examples(ds), "summary": "پرس‌وجوی فقط‌خواندنی روی جدول‌های تحلیلی BIAP.", "blocks": [], "missing": [], "provenance": ds["provenance"], "quality": ds["quality"]}
    result = mc.compute(module, ds, md.UNIVERSE.rows(STORE), params)
    if isinstance(result, dict):
        result["dataStatus"] = ds["status"]
    return result


def _sql_examples(ds: dict) -> list[dict]:
    sym = ds["identity"].get("symbol")
    sector = ds["identity"].get("sector")
    ex = [{"title": "این شرکت", "sql": "SELECT symbol, tier, price, pe, net_margin, roe, debt_ratio FROM companies WHERE code = ?", "params": [ds["identity"]["code"]]},
          {"title": "پرسودترین شرکت‌ها", "sql": "SELECT symbol, sector, net_margin, roe FROM companies WHERE net_margin IS NOT NULL ORDER BY net_margin DESC", "params": []},
          {"title": "پوشش داده به تفکیک سطح", "sql": "SELECT tier, COUNT(*) AS n FROM companies GROUP BY tier ORDER BY n DESC", "params": []}]
    if sector:
        ex.append({"title": "میانگین صنعت", "sql": "SELECT sector, COUNT(*) n, AVG(net_margin) avg_margin, AVG(pe) avg_pe FROM companies WHERE sector = ? GROUP BY sector", "params": [sector]})
    if sym:
        ex.append({"title": "تاریخچه قیمت", "sql": "SELECT date, price, change_percent FROM market_history WHERE symbol = ? ORDER BY date", "params": [sym]})
    return ex


def _symbol_variants(symbol: str) -> list[str]:
    out: list[str] = []
    for cand in (symbol, symbol.replace("ی", "ي").replace("ک", "ك"), symbol.replace("ي", "ی").replace("ك", "ک"), symbol.replace("\u200c", "")):
        if cand not in out:
            out.append(cand)
    return out


def _sql_database() -> Any:
    universe = md.UNIVERSE.rows(STORE)
    wanted = [r for r in universe if r.get("has_market") and r.get("symbol")]
    variants = {r["symbol"]: _symbol_variants(r["symbol"]) for r in wanted}
    snaps = history_for_symbols([v for vs in variants.values() for v in vs], days=400)  # one connection for the whole universe
    history = []
    for row in wanted:
        rows = next((snaps[v] for v in variants[row["symbol"]] if snaps.get(v)), [])
        for h in rows:
            history.append({"symbol": row["symbol"], "date": h.get("observed_date"), "price": h.get("price"), "change_percent": h.get("change_percent"),
                            "pe": h.get("pe"), "market_cap": h.get("market_cap"), "source": h.get("source")})
    return safe_sql.build_database(universe, history)


def _execute(body: dict) -> dict:
    conn = _sql_database()
    try:
        if body.get("spec") is not None:
            sql, params = safe_sql.structured_to_sql(body["spec"])
        else:
            sql, params = body.get("sql") or "", body.get("params") or []
        return safe_sql.run(conn, sql, params, limit=int(body.get("limit") or safe_sql.DEFAULT_ROWS), offset=int(body.get("offset") or 0))
    except safe_sql.QueryError as exc:
        raise ModuleError(400, "BAD_QUERY", str(exc)) from exc
    finally:
        conn.close()


@router.get("/sql/schema")
def sql_schema(_user: str = Depends(require_user_id)):
    return {"schema": safe_sql.schema(), "maxRows": safe_sql.MAX_ROWS, "timeBudgetSeconds": safe_sql.TIME_BUDGET_SECONDS}


@router.post("/sql/query")
def sql_query(body: dict = Body(...), _user: str = Depends(require_user_id)):
    return _execute(body)


@router.post("/sql/export", response_class=PlainTextResponse)
def sql_export(body: dict = Body(...), _user: str = Depends(require_user_id)):
    body = {**body, "limit": safe_sql.MAX_ROWS}
    return PlainTextResponse(safe_sql.to_csv(_execute(body)), media_type="text/csv; charset=utf-8")


# ---- private CRM / KPI register --------------------------------------------------------------

def _wrap(fn, *args):
    try:
        return fn(*args)
    except PrivateDataError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/crm/pipeline")
def crm_pipeline(user_id: str = Depends(require_user_id)):
    return PRIVATE.pipeline(user_id)


@router.get("/crm/contacts")
def crm_contacts(q: Optional[str] = Query(default=None, max_length=80), limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0), user_id: str = Depends(require_user_id)):
    return {"items": PRIVATE.list_contacts(user_id, q, limit, offset)}


@router.post("/crm/contacts")
def crm_contact_add(body: dict = Body(...), user_id: str = Depends(require_user_id)):
    return _wrap(PRIVATE.add_contact, user_id, body)


@router.put("/crm/contacts/{cid}")
def crm_contact_update(cid: int, body: dict = Body(...), user_id: str = Depends(require_user_id)):
    return _wrap(PRIVATE.update_contact, user_id, cid, body)


@router.delete("/crm/contacts/{cid}")
def crm_contact_delete(cid: int, user_id: str = Depends(require_user_id)):
    PRIVATE.delete_contact(user_id, cid)
    return {"deleted": True}


@router.get("/crm/leads")
def crm_leads(stage: Optional[str] = None, limit: int = Query(default=200, ge=1, le=500), offset: int = Query(default=0, ge=0), user_id: str = Depends(require_user_id)):
    return {"items": PRIVATE.list_leads(user_id, stage, limit, offset)}


@router.post("/crm/leads")
def crm_lead_add(body: dict = Body(...), user_id: str = Depends(require_user_id)):
    return _wrap(PRIVATE.add_lead, user_id, body)


@router.put("/crm/leads/{lid}")
def crm_lead_update(lid: int, body: dict = Body(...), user_id: str = Depends(require_user_id)):
    return _wrap(PRIVATE.move_lead, user_id, lid, body)


@router.delete("/crm/leads/{lid}")
def crm_lead_delete(lid: int, user_id: str = Depends(require_user_id)):
    PRIVATE.delete_lead(user_id, lid)
    return {"deleted": True}


@router.get("/crm/activities")
def crm_activities(leadId: Optional[int] = None, limit: int = Query(default=100, ge=1, le=500), user_id: str = Depends(require_user_id)):
    return {"items": PRIVATE.list_activities(user_id, leadId, limit)}


@router.post("/crm/activities")
def crm_activity_add(body: dict = Body(...), user_id: str = Depends(require_user_id)):
    return _wrap(PRIVATE.add_activity, user_id, body)


@router.get("/kpi-register")
def kpi_list(user_id: str = Depends(require_user_id)):
    return {"items": PRIVATE.list_kpis(user_id)}


@router.post("/kpi-register")
def kpi_add(body: dict = Body(...), user_id: str = Depends(require_user_id)):
    return _wrap(PRIVATE.upsert_kpi, user_id, body)


@router.put("/kpi-register/{kid}")
def kpi_update(kid: int, body: dict = Body(...), user_id: str = Depends(require_user_id)):
    return _wrap(PRIVATE.upsert_kpi, user_id, body, kid)


@router.delete("/kpi-register/{kid}")
def kpi_delete(kid: int, user_id: str = Depends(require_user_id)):
    PRIVATE.delete_kpi(user_id, kid)
    return {"deleted": True}


# ---- coverage --------------------------------------------------------------------------------

def coverage_report(all_rows: list[dict]) -> dict:
    """Coverage over genuine primary companies (one per issuer); non-primary instruments are counted separately."""
    universe = [r for r in all_rows if r.get("is_primary", 1)]
    total = len(universe)
    by_tier: dict[str, int] = {}
    for r in universe:
        by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + 1
    market = sum(1 for r in universe if r["has_market"])
    codal = sum(1 for r in universe if r["has_codal"])
    cfo = sum(1 for r in universe if r["has_codal"] and r.get("operating_cash_flow") is not None)
    ratios_ok = sum(1 for r in universe if sum(1 for k in md.UNIVERSE_RATIO_KEYS if r.get(k) is not None) >= 6)
    pct = lambda n: round(100 * n / total, 2) if total else 0.0  # noqa: E731
    return {
        "registered": total, "storedInstrumentRows": len(all_rows), "nonPrimaryInstrumentRows": len(all_rows) - total, "tiers": by_tier,
        "sources": {"market": {"count": market, "pct": pct(market)}, "codalFinancials": {"count": codal, "pct": pct(codal)},
                    "codalWithCashFlow": {"count": cfo, "pct": pct(cfo)}, "ratiosComputable(>=6)": {"count": ratios_ok, "pct": pct(ratios_ok)}},
        "reasons": {"noMarketPrice": total - market, "noCodalStatement": total - codal, "codalWithoutCashFlow": codal - cfo},
        "markets": {m: sum(1 for r in universe if (r.get("market") or "").upper() == m) for m in sorted({(r.get("market") or "").upper() for r in universe})},
    }


@router.get("/coverage")
def coverage(_user: str = Depends(require_user_id)):
    rep = coverage_report(md.UNIVERSE.rows(STORE))
    rep["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return rep
