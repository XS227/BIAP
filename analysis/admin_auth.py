"""Session handling for the BIAP admin panel.

Deliberately separate from analysis/auth.py (end-user ownership/JWT). Admin
identity comes from admin_store.py's own operator table, never from a
mobile-app user token, since there is currently no way to verify that a
caller claiming to be an admin is actually one of the small named set of
people who run BIAP (see admin_store.py's module docstring).

A successful login issues a short-lived JWT (reusing PyJWT, already a
dependency) carrying the operator's username, stored in an HttpOnly,
SameSite=Strict cookie -- not the Authorization header, since this is a
browser-rendered panel, not an API client. Every audit event the admin
panel writes records this username as the actor, so approvals/rejections
made here are attributable to a person, unlike the existing shared
BIAP_APPROVER_TOKEN used by the JSON API in api_server.py.

Fails closed like auth.require_approver: an unconfigured secret refuses
every session rather than falling back to something weaker.
"""

from __future__ import annotations

import os
import time

from fastapi import Request
import jwt as pyjwt


COOKIE_NAME = "biap_admin_session"
SESSION_TTL_SECONDS = 12 * 60 * 60  # 12h -- an operator shift, not a persistent login


class AdminAuthRequired(Exception):
    """Raised by require_admin; caught by an exception handler that redirects to /admin/login."""


def _secret() -> str:
    return os.environ.get("BIAP_ADMIN_JWT_SECRET", "")


def admin_panel_configured() -> bool:
    return bool(_secret())


def create_session_token(username: str) -> str:
    secret = _secret()
    if not secret:
        raise RuntimeError("BIAP_ADMIN_JWT_SECRET is not configured")
    now = int(time.time())
    payload = {"sub": username, "role": "admin", "iat": now, "exp": now + SESSION_TTL_SECONDS}
    return pyjwt.encode(payload, secret, algorithm="HS256")


def verify_session_token(token: str) -> str | None:
    secret = _secret()
    if not secret or not token:
        return None
    try:
        payload = pyjwt.decode(token, secret, algorithms=["HS256"])
    except pyjwt.PyJWTError:
        return None
    username = payload.get("sub")
    return username if payload.get("role") == "admin" and username else None


def require_admin(request: Request) -> str:
    """FastAPI dependency: returns the logged-in operator's username or raises AdminAuthRequired."""
    if not admin_panel_configured():
        raise AdminAuthRequired()
    token = request.cookies.get(COOKIE_NAME, "")
    username = verify_session_token(token)
    if username is None:
        raise AdminAuthRequired()
    return username
