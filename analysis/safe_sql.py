"""Read-only analytical SQL over a private in-memory copy of BIAP's normalized tables.

The mobile app never touches the production databases: each request builds an in-memory SQLite
database from the cached universe table (+ market history), locks it with ``query_only``, an
authorizer (SELECT of whitelisted tables and functions only), a row cap and a wall-clock budget.
Queries are either a structured spec (identifiers whitelisted, values bound as parameters) or a single
SELECT statement with ``?`` parameters.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
import time
from typing import Any, Iterable, Optional

MAX_ROWS = 1000
DEFAULT_ROWS = 200
TIME_BUDGET_SECONDS = 3.0
MAX_SQL_CHARS = 2000

COMPANY_COLUMNS = {
    "code": "TEXT", "symbol": "TEXT", "symbol_key": "TEXT", "name": "TEXT", "market": "TEXT", "sector": "TEXT", "tier": "TEXT",
    "has_market": "INTEGER", "has_codal": "INTEGER", "scope": "TEXT", "period_type": "TEXT", "tracing_no": "TEXT",
    "price": "REAL", "change_percent": "REAL", "pe": "REAL", "eps": "REAL", "market_cap": "REAL", "volume": "REAL", "trade_value": "REAL",
    "revenue": "REAL", "net_profit": "REAL", "operating_profit": "REAL", "gross_profit": "REAL", "total_assets": "REAL",
    "total_equity": "REAL", "total_liabilities": "REAL", "current_assets": "REAL", "current_liabilities": "REAL", "operating_cash_flow": "REAL",
    "gross_margin": "REAL", "operating_margin": "REAL", "net_margin": "REAL", "roa": "REAL", "roe": "REAL", "debt_ratio": "REAL",
    "debt_to_equity": "REAL", "current_ratio": "REAL", "revenue_growth": "REAL", "profit_growth": "REAL", "cfo_to_profit": "REAL",
    "accruals_ratio": "REAL", "asset_turnover": "REAL", "receivable_days": "REAL", "enriched_at": "TEXT",
    "is_primary": "INTEGER", "category": "TEXT", "issuer_id": "TEXT",
}
HISTORY_COLUMNS = {"symbol": "TEXT", "date": "TEXT", "price": "REAL", "change_percent": "REAL", "pe": "REAL", "market_cap": "REAL", "source": "TEXT"}
TABLES = {"companies": COMPANY_COLUMNS, "market_history": HISTORY_COLUMNS}

ALLOWED_FUNCTIONS = {"count", "sum", "avg", "min", "max", "round", "abs", "lower", "upper", "length", "coalesce", "ifnull", "nullif",
                     "substr", "total", "group_concat", "typeof", "iif", "cast", "like", "glob", "instr", "trim", "ltrim", "rtrim", "replace"}
OPS = {"=": "=", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">=", "like": "LIKE", "is_null": "IS NULL", "not_null": "IS NOT NULL"}
AGGS = {"count", "sum", "avg", "min", "max"}


class QueryError(ValueError):
    pass


def build_database(companies: Iterable[dict], history: Iterable[dict] = ()) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    for table, cols in TABLES.items():
        conn.execute(f"CREATE TABLE {table} ({', '.join(f'{c} {t}' for c, t in cols.items())})")
    ccols = list(COMPANY_COLUMNS)
    conn.executemany(f"INSERT INTO companies ({','.join(ccols)}) VALUES ({','.join('?' * len(ccols))})",
                     ([row.get(c) for c in ccols] for row in companies))
    hcols = list(HISTORY_COLUMNS)
    conn.executemany(f"INSERT INTO market_history ({','.join(hcols)}) VALUES ({','.join('?' * len(hcols))})",
                     ([h.get(c) for c in hcols] for h in history))
    conn.commit()
    return conn


def _lock_down(conn: sqlite3.Connection, deadline: float) -> None:
    conn.execute("PRAGMA query_only=ON")

    def authorizer(action, arg1, arg2, dbname, source):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            return sqlite3.SQLITE_OK if arg1 in TABLES and (arg2 in TABLES[arg1] or arg2 == "") else sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION:
            return sqlite3.SQLITE_OK if str(arg2).lower() in ALLOWED_FUNCTIONS else sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_DENY

    conn.set_authorizer(authorizer)
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 20000)


def _validate_sql(sql: str) -> str:
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql or len(sql) > MAX_SQL_CHARS:
        raise QueryError("empty or too long query")
    if ";" in sql:
        raise QueryError("only a single statement is allowed")
    if "--" in sql or "/*" in sql:
        raise QueryError("comments are not allowed")
    if not re.match(r"(?is)^(select|with)\b", sql):
        raise QueryError("only SELECT queries are allowed")
    return sql


def run(conn: sqlite3.Connection, sql: str, params: Optional[list] = None, *, limit: int = DEFAULT_ROWS, offset: int = 0,
        clock=time.monotonic) -> dict:
    sql = _validate_sql(sql)
    limit = max(1, min(int(limit), MAX_ROWS))
    offset = max(0, int(offset))
    params = list(params or [])
    if len(params) > 50 or any(not isinstance(p, (str, int, float, type(None))) for p in params):
        raise QueryError("invalid parameters")
    _lock_down(conn, clock() + TIME_BUDGET_SECONDS)
    started = clock()
    try:
        cur = conn.execute(f"SELECT * FROM ({sql}) LIMIT ? OFFSET ?", [*params, limit + 1, offset])
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description or []]
    except sqlite3.OperationalError as exc:
        text = str(exc)
        if "interrupted" in text:
            raise QueryError("query exceeded the time budget") from exc
        raise QueryError(f"query rejected: {text}") from exc
    except sqlite3.DatabaseError as exc:
        raise QueryError(f"query rejected: {exc}") from exc
    finally:
        conn.set_authorizer(None)
        conn.set_progress_handler(None, 0)
    truncated = len(rows) > limit
    return {"columns": cols, "rows": [list(r) for r in rows[:limit]], "rowCount": min(len(rows), limit), "truncated": truncated,
            "limit": limit, "offset": offset, "elapsedMs": round((clock() - started) * 1000, 1)}


def structured_to_sql(spec: dict) -> tuple[str, list]:
    """{table, columns?, aggregates?[{fn,column,as?}], groupBy?, where?[{column,op,value}], orderBy?[{column,dir}]}"""
    table = spec.get("table")
    if table not in TABLES:
        raise QueryError(f"unknown table {table!r}")
    allowed = set(TABLES[table])

    def col(name: Any) -> str:
        if name not in allowed:
            raise QueryError(f"unknown column {name!r}")
        return str(name)

    select: list[str] = []
    aliases: set[str] = set()
    for c in spec.get("columns") or []:
        select.append(col(c)); aliases.add(str(c))
    for agg in spec.get("aggregates") or []:
        fn = str(agg.get("fn", "")).lower()
        if fn not in AGGS:
            raise QueryError(f"unsupported aggregate {fn!r}")
        target = "*" if (fn == "count" and agg.get("column") in (None, "*")) else col(agg.get("column"))
        alias = re.sub(r"[^a-z0-9_]", "", str(agg.get("as") or f"{fn}_{'all' if target == '*' else target}").lower()) or fn
        select.append(f"{fn.upper()}({target}) AS {alias}"); aliases.add(alias)
    if not select:
        select = list(COMPANY_COLUMNS if table == "companies" else HISTORY_COLUMNS)
    sql = f"SELECT {', '.join(select)} FROM {table}"
    params: list = []
    clauses = []
    for w in spec.get("where") or []:
        op = str(w.get("op", "=")).lower()
        if op not in OPS:
            raise QueryError(f"unsupported operator {op!r}")
        c = col(w.get("column"))
        if op in ("is_null", "not_null"):
            clauses.append(f"{c} {OPS[op]}")
        else:
            value = w.get("value")
            if not isinstance(value, (str, int, float)):
                raise QueryError("filter value must be a string or number")
            clauses.append(f"{c} {OPS[op]} ?")
            params.append(value)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    group = [col(c) for c in spec.get("groupBy") or []]
    if group:
        sql += " GROUP BY " + ", ".join(group)
    order = []
    for o in spec.get("orderBy") or []:
        name = o.get("column")
        if name not in allowed and name not in aliases:
            raise QueryError(f"unknown order column {name!r}")
        order.append(f"{name} {'DESC' if str(o.get('dir', 'asc')).lower() == 'desc' else 'ASC'}")
    if order:
        sql += " ORDER BY " + ", ".join(order)
    return sql, params


def to_csv(result: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(result["columns"])
    for row in result["rows"]:
        writer.writerow(["" if v is None else v for v in row])
    return buf.getvalue()


def schema() -> dict:
    return {t: [{"name": c, "type": ty} for c, ty in cols.items()] for t, cols in TABLES.items()}
