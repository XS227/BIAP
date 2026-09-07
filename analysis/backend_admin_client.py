"""Account/admin analytics adapter for the production FIN auth store.

Production authentication is served by ``analysis/local_auth.py`` on biap-fin,
so admin analytics must read that same SQLite database. Keeping this adapter's
``get_json`` shape lets the existing /admindir pages stay unchanged while
avoiding a second Node/Postgres user store.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from account_ops_local import account_summary, list_activity, list_installs, list_users


class BackendAdminUnavailable(RuntimeError):
    pass


def configured() -> bool:
    # /admindir is already protected by the separate admin session. This is an
    # in-process read of the same production auth database, so no second shared
    # secret or HTTP hop is needed.
    return True


def get_json(path: str, *, params: dict[str, str | int | None] | None = None, timeout: float = 6.0) -> dict[str, Any]:
    del timeout  # compatibility with the old HTTP-client signature
    normalized = "/" + path.strip("/")
    params = params or {}
    try:
        if normalized == "/admin/ops/summary":
            return account_summary()
        if normalized == "/admin/ops/users":
            return {"items": list_users(int(params.get("limit") or 200))}
        if normalized == "/admin/ops/installs":
            return {"items": list_installs(int(params.get("limit") or 250))}
        if normalized == "/admin/ops/activity":
            raw_user = params.get("userId")
            user_id = str(raw_user) if raw_user not in (None, "") else None
            return {"items": list_activity(int(params.get("limit") or 300), user_id=user_id)}
    except (OSError, ValueError, sqlite3.Error) as exc:
        raise BackendAdminUnavailable(str(exc)) from exc
    raise BackendAdminUnavailable(f"unsupported local admin path: {normalized}")
