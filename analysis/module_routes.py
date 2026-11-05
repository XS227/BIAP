"""Unified module-data service for the Iran app: one resolver, one dataset builder, one contract per module.

GET  /iran/modules/{code}/dataset         normalized market + CODAL dataset with provenance/quality
GET  /iran/modules/{code}/readiness       every module's contract status for this company
POST /iran/modules/{code}/{module}        compute a module (blocks the app renders generically)
GET  /iran/sql/schema | POST /iran/sql/query | POST /iran/sql/export
/iran/crm/*                               private CRM + KPI register (user-scoped)
GET  /iran/coverage                       whole-universe data coverage and reasons
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

import module_compute as mc
import module_dataset as md
import private_analytics
import safe_sql
from auth import require_user_id
from business_dataset_store import get_dataset
from codal_inbox import symbol_key
from listed_company_store import ListedCompanyStore
from market_memory import recent_symbol_history
from private_store import PrivateDataError, PrivateStore

router = APIRouter(prefix="/iran", tags=["iran-modules"])
STORE = ListedCompanyStore()
PRIVATE = PrivateStore()


def resolve_company(store: ListedCompanyStore, text: str) -> dict:
    """Instrument code first; otherwise the spelling-insensitive symbol (Arabic ي/ك, ZWNJ, spaces).

    Two different instruments with the same normalized symbol are an error with candidates -- never a guess.
    """
    text = (text or "").strip()
    with store._connect() as conn:
        row = conn.execute("SELECT code FROM listed_companies WHERE code=?", (text,)).fetchone()
        if row:
            return store.get(row["code"])
        wanted = symbol_key(text)
        if not wanted:
            raise HTTPException(status_code=404, detail="company not found")
        hits = [r for r in conn.execute("SELECT code, symbol, name_fa, market FROM listed_companies") if symbol_key(r["symbol"]) == wanted]
    if len(hits) == 1:
        return store.get(hits[0]["code"])
    if len(hits) > 1:
        exact = [h for h in hits if h["symbol"] == text]
        if len(exact) == 1:
            return store.get(exact[0]["code"])
        raise HTTPException(status_code=409, detail={"message": "ambiguous symbol", "candidates": [
            {"code": h["code"], "symbol": h["symbol"], "name": h["name_fa"], "market": h["market"]} for h in hits[:10]]})
    raise HTTPException(status_code=404, detail="company not found")


def dataset_for(code: str) -> dict:
    item = resolve_company(STORE, code)
    history = recent_symbol_history(item["symbol"], days=400) if item.get("symbol") else []
    return md.build_company_dataset(item, history, now_iso=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _peers(ds: dict, universe: list[dict]) -> int:
    sector = ds["identity"].get("sector")
    rows = [r for r in universe if r.get("has_codal") and r["code"] != ds["identity"]["code"]]
    same = [r for r in rows if sector and r.get("sector") == sector]
    return max(len(same), len(rows))


@router.get("/modules/{code}/dataset")
def module_dataset(code: str, _user: str = Depends(require_user_id)):
    return dataset_for(code)


@router.get("/modules/{code}/readiness")
def module_readiness(code: str, _user: str = Depends(require_user_id)):
    ds = dataset_for(code)
    universe = md.UNIVERSE.rows(STORE)
    return {"company": ds["identity"], "tier": ds["tier"], "modules": mc.readiness(ds, _peers(ds, universe)), "quality": ds["quality"]}


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
    return mc.compute(module, ds, md.UNIVERSE.rows(STORE), params)


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


def _sql_database() -> Any:
    universe = md.UNIVERSE.rows(STORE)
    history = []
    for row in universe:
        if row.get("has_market") and row.get("symbol"):
            for h in recent_symbol_history(row["symbol"], days=400):
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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

def coverage_report(universe: list[dict]) -> dict:
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
        "registered": total, "tiers": by_tier,
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
